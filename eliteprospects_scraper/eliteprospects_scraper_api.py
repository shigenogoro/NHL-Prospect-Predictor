'''
    API for Elite Prospects Scraper
    1. get_season_roster(league, season): Allows you to get all players from a specific league and season
    2. get_single_player_stats(url): Allows you to get all information from a player's webpage
'''

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
import requests
import time
from datetime import datetime
import re   #　Regular expressions

# Used to grab the part where JavaScript is used to load the data
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

'''
    The following functions are used to help with handle the table data and pagination
'''

# Helper function to extract data from a table - return a list with rows data frame
def table_data_to_rows(table):
    '''
        Helper function to extract data from a table
        Parameters:
            table (bs4.element.Tag): Table to extract data from
        Returns:
            rows (list): List with rows data frame
    '''
    rows = []
    trs = table.find_all('tr')

    headerrow = [td.get_text(strip=True) for td in trs[0].find_all('th')] # header row
    if headerrow: # if there is a header row include first
        rows.append(headerrow)
        trs = trs[1:]
    for tr in trs: # for every table row
        rows.append([td.get_text(strip=True) for td in tr.find_all('td')]) # data row

    df_rows = pd.DataFrame(rows[1:], columns=rows[0])
    return df_rows

# Helper function to extract number of pages
def get_number_of_pages(url):
    '''
        Helper function to extract the number of pages in a table
        Parameters:
            url (str): URL to extract the number of pages from
        Returns:
            num_pages (int): Number of pages
    '''
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
    else:
        return 0

# Helper function to merge regular season and postseason stats
def merge_stats(df_regular, df_postseason):
    '''
        Helper function to merge regular season and postseason stats
        Parameters:
            df_regular (pd.DataFrame): DataFrame with regular season stats
            df_postseason (pd.DataFrame): DataFrame with postseason stats
        Returns:
            df (pd.DataFrame): DataFrame with merged stats
    '''
    # Merge the two dataframes on season, team and league
    full_stats_df = df_regular.merge(df_postseason, on=['season', 'team', 'league'], how='left')

    return full_stats_df


'''
    The following functions are used to handle the player's stats
'''

def get_season_roster(league, season):
    '''
        Get all players from a specific league and season
        Parameters:
            league (str): Name of the league
            season (str): Name of the season
        Returns:
            df (pd.DataFrame): DataFrame with all players
    '''
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

                # Create a data frame, rename and only keep those players with link
                df_links = pd.DataFrame(href_row)
                df_links.rename(columns={df_links.columns[0]: "link"}, inplace=True)
                df_links = df_links[df_links['link'].str.contains("/player/")].reset_index(drop=True)

                # Add links to players
                df_players['link'] = df_links['link']
                players.append(df_players)

                # Wait 3 seconds before going to the next page
                time.sleep(3)

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
    '''
        Get player's metadata from df_players
        Parameters:
            df_players (pd.DataFrame): DataFrame with all players
        Returns:
            df_players (pd.DataFrame): DataFrame with all players and metadata
    '''

    # Get distinct players
    players_meta = df_players[['playername', 'fw_def', 'link']].drop_duplicates().reset_index(drop=True)
    return players_meta

def get_single_player_stats_by_type(player_url, stat_type='Regular Season'):
    '''
        Get player's stats from a player's webpage
        Parameters:
            player_url (str): URL to the player's webpage
        Returns:
            df_stats (pd.DataFrame): DataFrame with all player's stats
    '''
    # Parameters Checking
    valid_stat_types = ["Regular Season", "Postseason"]
    if stat_type not in valid_stat_types:
        raise ValueError(f"Invalid stat type. Valid stat types are: {', '.join(valid_stat_types)}")

    # Players Stats on their webpage are loaded using JavaScript
    # Use Selenium to load the page and extract the stats
    # Set up Selenium
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run Chrome in headless mode (no GUI)
    chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
    chrome_options.add_argument("--disable-dev-shm-usage")  # Disable /dev/shm usage

    # Initialize the Chrome WebDriver
    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 10)

    # Load the player's webpage
    driver.get(player_url)
    time.sleep(3) # Wait for the page to load

    # Manipulate the dropdown manu for regular season or postseason
    # Step 1: Click the dropdown control (the clickable box)
    dropdown_control = wait.until(
        EC.element_to_be_clickable((By.CLASS_NAME, "css-x1uf2d-control"))
    )

    # Scroll into view
    driver.execute_script("arguments[0].scrollIntoView(true);", dropdown_control)
    time.sleep(0.5)

    dropdown_control.click()
    time.sleep(1)

    # Step 2: Find the hidden input inside dropdown and type the desired option
    input_box = driver.find_element(By.ID, "react-select-player-statistics-default-season-selector-league-input")
    input_box.send_keys(stat_type)
    input_box.send_keys(Keys.ENTER)

    # Wait for table to update
    time.sleep(3)

    # Get fully rendered HTML
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    player_table = soup.find('table', {'class': 'SortTable_table__jnnJk PlayerStatistics_mobileColumnWidth__4eS8P'})

    # Close the WebDriver
    driver.quit()

    # Check if the table exists
    if player_table is not None:
        df_stats = table_data_to_rows(player_table)

        # Convert all column names to the lowercase
        df_stats.columns = [col_name.lower() for col_name in df_stats.columns]
        df_stats.rename(columns={'s': 'season'}, inplace=True)

        return df_stats

    return None

def get_single_player_stats(player_url):
    '''
        Get player's stats from a player's webpage
        Parameters:
            player_url (str): URL to the player's webpage
        Returns:
            df_stats (pd.DataFrame): DataFrame with all player's stats
    '''
    # Get regular season stats
    df_regular = get_single_player_stats_by_type(player_url, 'Regular Season')

    # Get postseason stats
    df_postseason = get_single_player_stats_by_type(player_url, 'Postseason')

    # Merge the two dataframes
    df_stats = merge_stats(df_regular, df_postseason)

    # Rename the columns
    df_stats.rename(columns={
        'gp_x': 'gp_regular',
        'g_x': 'g_regular',
        'a_x': 'a_regular',
        'tp_x': 'tp_regular',
        'pim_x': 'pim_regular',
        '+/-_x': '+/-_regular',
        'gp_y': 'gp_post',
        'g_y': 'g_post',
        'a_y': 'a_post',
        'tp_y': 'tp_post',
        'pim_y': 'pim_post',
        '+/-_y': '+/-_post'
    }, inplace=True)

    return df_stats

def get_players_stats(players_meatadata):
    '''
        Get all players' stats from a list of player links
        Parameters:
            player_links (list): List of player links
        Returns:
            df_stats (pd.DataFrame): DataFrame with all players' stats
    '''
    # Get Players' Name and Links
    players_links = players_meatadata['link'].tolist()
    players_names = players_meatadata['playername'].tolist()

    # Get all players' stats
    players_stats = pd.DataFrame()
    for i in range(len(players_links)):
        print(f"Collecting data from {players_links[i]}")
        player_stats = get_single_player_stats(players_links[i])
        player_stats['playername'] = players_names[i]
        players_stats = pd.concat([players_stats, player_stats]).reset_index(drop=True)
        time.sleep(5)

    # Move the playername column to the front
    playersname_col = players_stats.iloc[:, -1]
    other_cols = players_stats.iloc[:, :-1]

    # Combine
    players_stats = pd.concat([playersname_col, other_cols], axis=1)

    return players_stats

'''
    The following functions are used to handle the goalie's stats
'''