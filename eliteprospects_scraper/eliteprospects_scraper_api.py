'''
    API for Elite Prospects Scraper
    1. getSeasonRoster(league, season): Allows you to get all players from a specific league and season
    2. getPlayer(url): Allows you to get all information from a player's webpage
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

'''
    The following functions are used to help with handle the table data and pagination
'''

# Helper Function to extract data from a table - return a list with rows data frame
def tableDataToRows(table):
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

# Helper Function to extract number of pages
def getNumberOfPages(url):
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

'''
    The following functions are used to handle the player's stats
'''

def getSeasonRoster(league, season):
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
    num_pages = getNumberOfPages(url)

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
            df_players = tableDataToRows(player_table)

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

def getPlayersMetadata(df_players):
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

'''
    The following functions are used to handle the goalie's stats
'''