"""
    API for Elite Prospects Scraper
    1. get_season_roster(league, season): Allows you to get all players from a specific league and season
    2. get_single_player_stats(url): Allows you to get all information from a player's webpage
"""

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
import requests
import time
import re   #　Regular expressions
import random

# Used to grab the part where JavaScript is used to load the data
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
import undetected_chromedriver as uc

'''
    The following functions are used to help with handle the table data and pagination
'''

# Helper function to extract data from a table - return a list with rows data frame
def table_data_to_rows(table):
    """
        Helper function to extract data from a table
        Parameters:
            table (bs4.element.Tag): Table to extract data from
        Returns:
            rows (list): List with rows data frame
    """
    rows = []
    trs = table.find_all('tr')

    header_row = [td.get_text(strip=True) for td in trs[0].find_all('th')] # header row
    if header_row: # if there is a header row include first
        rows.append(header_row)
        trs = trs[1:]
    for tr in trs: # for every table row
        rows.append([td.get_text(strip=True) for td in tr.find_all('td')]) # data row

    df_rows = pd.DataFrame(rows[1:], columns=rows[0])
    return df_rows

# Helper function to extract the number of pages
def get_number_of_pages(url):
    """
        Helper function to extract the number of pages in a table
        Parameters:
            url (str): URL to extract the number of pages from
        Returns:
            num_pages (int): Number of pages
    """
    # Get the page
    page = requests.get(url)
    soup = BeautifulSoup(page.text, 'html.parser')

    # Find the div
    pagination_div = soup.find('div', {'class': 'table-pagination'})

    # Extract text and find the number using regex
    if pagination_div:
        text = pagination_div.get_text(strip=True)
        match =re.search(r'([\d\s]+)players found', text)
        if match:
            # Extract the number of players
            raw_number = match.group(1)
            num_players = int(raw_number.replace(' ', ''))  # Remove space for thousands
            print(f'total number of players found = {num_players}')

            # Get the total number of pages
            num_pages = num_players // 100 + 1
            print(f'total number of pages = {num_pages}')
            return num_pages
        return 0
    else:
        return 0

# Helper function to merge regular season and postseason stats
def merge_stats(df_regular, df_postseason):
    """
        Helper function to merge regular season and postseason stats
        Parameters:
            df_regular (pd.DataFrame): DataFrame with regular season stats
            df_postseason (pd.DataFrame): DataFrame with postseason stats
        Returns:
            df (pd.DataFrame): DataFrame with merged stats
    """
    required_columns = {'season', 'team', 'league'}

    # Sanity check
    if not required_columns.issubset(df_regular.columns) or not required_columns.issubset(df_postseason.columns):
        print("Merge failed due to missing columns.")
        print("Regular season columns:", df_regular.columns.tolist())
        print("Postseason columns:", df_postseason.columns.tolist())
        return pd.concat([df_regular, df_postseason], ignore_index=True)

    # Merge with suffixes
    df_merged = df_regular.merge(
        df_postseason,
        on=['playername', 'season', 'team', 'league'],
        how='left',
        suffixes=('_regular', '_post')
    )

    return df_merged

# Helper function to standardize the column names
def standardize_stat_columns(df):
    rename_map = {
        's': 'season',
        'tm': 'team',
        'team': 'team',
        'lg.': 'league',
        'league': 'league',
        'year': 'season'
    }
    return df.rename(columns={col: rename_map.get(col.lower(), col.lower()) for col in df.columns})

# Helper Function to Get Player's Stats
def get_stats(driver, wait, player_name, stat_name):
    try:
        # Click dropdown
        dropdown = wait.until(ec.element_to_be_clickable((By.CLASS_NAME, "css-x1uf2d-control")))
        driver.execute_script("arguments[0].scrollIntoView(true);", dropdown)
        dropdown.click()
        time.sleep(0.3)

        # Input stat type and hit Enter
        input_box = driver.find_element(By.ID, "react-select-player-statistics-default-season-selector-league-input")
        input_box.send_keys(stat_name)
        input_box.send_keys(Keys.ENTER)
        time.sleep(random.uniform(1.5, 2.0))

        soup = BeautifulSoup(driver.page_source, "html.parser")
        table = soup.find("table", class_="SortTable_table__jnnJk PlayerStatistics_mobileColumnWidth__4eS8P")

        # Append playername to the table
        player_stats = table_data_to_rows(table)
        player_stats['playername'] = player_name

        # Move the playername column to the front
        playername_col = player_stats.iloc[:, -1]
        other_cols = player_stats.iloc[:, :-1]
        player_stats = pd.concat([playername_col, other_cols], axis=1)

        # Modified the column name to lowercase
        player_stats.columns = [col.lower() for col in player_stats.columns]

        # Standardize the column names
        player_stats = standardize_stat_columns(player_stats)

        return player_stats
    except Exception as e:
        print(f"Failed to get '{stat_name}' table: {e}")
        return None


'''
    The following functions are used to handle the player's stats
'''

def get_season_roster(league, season):
    """
        Get all players from a specific league and season
        Parameters:
            league (str): Name of the league
            season (str): Name of the season
        Returns:
            df (pd.DataFrame): DataFrame with all players
    """
    # Check if the league and season are valid
    valid_leagues = ["nhl", "ahl", "echl", "sphl", "ncaa",
                    "whl", "ohl", "qmjhl", "ushl", "nahl",
                    "khl", "shl", "liiga", "nl", "czechia",
                    "slovakia", "latvia", "finland"]

    # Validate the league
    if league not in valid_leagues:
        raise ValueError(f"Invalid league. Valid leagues are: {', '.join(valid_leagues)}")

    # Validate the season format
    if not re.match(r'^\d{4}-\d{4}$', season):
        raise ValueError("Invalid season format. Please use the format 'YYYY-YYYY'")

    # Get the URL
    url = 'https://www.eliteprospects.com/league/' + league + '/stats/' + season
    num_pages = get_number_of_pages(url)

    # Initiate a list of players
    players = []

    # Loop through all pages
    url += '/?page='
    for i in range(1, num_pages + 1):
        # Get the page
        page = requests.get(url + str(i))
        print(f"Collecting data from {url + str(i)}")
        soup = BeautifulSoup(page.content, 'html.parser')

        # Get the table
        player_table = soup.find('table', {'class': 'table table-striped table-sortable player-stats highlight-stats season'})

        # Check if the table exists
        if player_table is not None:
            df_players = table_data_to_rows(player_table)

            # Player exists in the table
            if df_players['#'].count() > 0:
                # Remove empty rows (where # is empty)
                df_players = df_players[df_players['#'] != ''].reset_index(drop=True)

                # Extract href links in the table
                href_row = []
                for link in player_table.find_all('a'):
                    href_row.append(link.attrs['href'])

                # Create a data frame, rename and only keep those players with the link
                df_links = pd.DataFrame(href_row)
                df_links.rename(columns={df_links.columns[0]: "link"}, inplace=True)
                df_links = df_links[df_links['link'].str.contains("/player/")].reset_index(drop=True)

                # Add links to players
                df_players['link'] = df_links['link']
                players.append(df_players)

                # Wait 3 seconds before going to the next page
                time.sleep(random.uniform(1, 3))

    # Concatenate all the pages into one DataFrame
    df_players = pd.concat(players).reset_index()

    # Convert all column names to the lowercase
    df_players.columns = [col_name.lower() for col_name in df_players.columns]

    # Clean up the dataset
    df_players['season'] = season
    df_players['league'] = league

    df_players = df_players.drop(['index', '#'], axis=1).reset_index(drop=True)

    # Strip any "(position)" from the player string to get the name
    df_players['playername'] = df_players['player'].str.replace(r'\s*\(.*?\)', "", regex=True)
    # Extracts the text inside the parentheses as the position
    df_players['position'] = df_players['player'].str.extract(r'\((.*?)\).*')

    # Tag Forward or Defenseman as FW or DEF
    df_players['fw_def'] = np.where(
        df_players['position'].str.contains('D'), 'DEF', 'FW'
    )

    # # Clean Team Column - Remove Unwanted Special Characters
    team = df_players['team'].str.split("“", n=1, expand=True)
    df_players['team'] = team[0]

    # Drop the original player column
    df_players.drop(['player'], axis=1)

    return df_players

def get_players_metadata(df_players):
    """
        Get player's metadata from df_players
        Parameters:
            df_players (pd.DataFrame): DataFrame with all players
        Returns:
            df_players (pd.DataFrame): DataFrame with all players and metadata
    """

    # Get distinct players
    players_meta = df_players[['playername', 'fw_def', 'link']].drop_duplicates().reset_index(drop=True)
    return players_meta


def get_player_stats(player_metadata, stats_type="Regular Season + Postseason"):
    """
    Get a player's stats from a player's webpage.

    Parameters:
        player_metadata (pd.Series): Series with 'playername' and 'link'.
        stats_type (str): "Regular Season", "Postseason", or "Regular Season + Postseason".

    Returns:
        result (pd.DataFrame or None): Combined stats DataFrame.
    """
    player_name = str(player_metadata['playername'])
    player_url = str(player_metadata['link'])

    print(f"\nCollecting {stats_type} stats for {player_name} at {player_url}")

    # Use uc.ChromeOptions, NOT selenium's Options
    chrome_options = uc.ChromeOptions()

    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = uc.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 15)
    result = None

    try:
        driver.get(player_url)
        time.sleep(random.uniform(1, 2))

        # Get data by stats_type
        result = get_stats(driver, wait, player_name, stats_type)

        if result is None:
            print(f"No stats found for {player_name}")

    except Exception as e:
        print(f"Error scraping {player_name}: {e}")

    finally:
        driver.quit()

    return result

'''
    The following functions are used to handle the goalie's stats
'''