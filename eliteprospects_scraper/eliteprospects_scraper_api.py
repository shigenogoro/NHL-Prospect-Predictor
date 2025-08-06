"""
    API for Elite Prospects Scraper
    1. get_season_roster(league, season): Allows you to get all players from a specific league and season
    2. get_player_stats(player_metadata, stats_type): Allows you to get all information from a player's webpage
    3. get_players_stats(players_metadata): Allows you to get all information from a list of players' webpage
    4. get_player_facts(player_metadata): Allows you to get all facts from a player's webpage
"""

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
import requests
import time
import re   #　Regular expressions
import random

# Used to grab the part where JavaScript is used to load the data
from selenium.common import ElementClickInterceptedException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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
        on=['player_name', 'season', 'team', 'league'],
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

        # Append player_name to the table
        player_stats = table_data_to_rows(table)
        player_stats['player_name'] = player_name

        # Move the player_name column to the front
        player_name_col = player_stats.iloc[:, -1]
        other_cols = player_stats.iloc[:, :-1]
        player_stats = pd.concat([player_name_col, other_cols], axis=1)

        # Modified the column name to lowercase
        player_stats.columns = [col.lower() for col in player_stats.columns]

        # Standardize the column names
        player_stats = standardize_stat_columns(player_stats)

        return player_stats
    except Exception as e:
        print(f"Failed to get '{stat_name}' table: {e}")
        return None

# Helper Function to Truncate Description
def truncate_description(text):
    """
    Truncate the description at the last complete sentence (last period).
    """
    if not text:
        return None
    last_period = text.rfind(".")
    return text[:last_period + 1] if last_period != -1 else text

# Helper Function to Extract Draft Info
def extract_draft_info(text):
    """
    Extracts (round, overall, year) as strings from a draft description like:
    '1rd round, 4th overall (2017)'
    """
    if not text:
        return None
    match = re.search(r"(\d+)[a-z]{2}\s+round,\s+(\d+)[a-z]{2}\s+overall\s+\((\d{4})\)", text.lower())
    if match:
        round_num = match.group(1)
        overall_num = match.group(2)
        year = match.group(3)
        return (round_num, overall_num, year)
    return None

# Helper Function to Convert NaN to None
def convert_NaN_to_None(df):
    return df.astype(object).where(pd.notnull(df), None)

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
    df_players['player_name'] = df_players['player'].str.replace(r'\s*\(.*?\)', "", regex=True)
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
    players_meta = df_players[['player_name', 'fw_def', 'link']].drop_duplicates().reset_index(drop=True)
    return players_meta


def get_player_stats(player_metadata, stats_type="Regular Season + Postseason"):
    """
    Get a player's stats from a player's webpage.

    Parameters:
        player_metadata (pd.Series): Series with 'player_name' and 'link'.
        stats_type (str): "Regular Season", "Postseason", or "Regular Season + Postseason".

    Returns:
        result (pd.DataFrame or None): Combined stats DataFrame.
    """
    player_name = str(player_metadata['player_name'])
    player_url = str(player_metadata['link'])

    print(f"Collecting {stats_type} stats for {player_name} at {player_url}")

    # Use uc.ChromeOptions, NOT selenium's Options
    chrome_options = uc.ChromeOptions()

    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = uc.Chrome(version_main=138, options=chrome_options)
    wait = WebDriverWait(driver, 15)
    result = None

    try:
        driver.get(player_url)
        time.sleep(random.uniform(1.5, 2.5))

        try:
            # Click dropdown if needed
            dropdown = wait.until(ec.element_to_be_clickable((By.CSS_SELECTOR, "div.css-x1uf2d-control")))
            driver.execute_script("arguments[0].scrollIntoView(true);", dropdown)
            time.sleep(0.5)
            dropdown.click()
        except ElementClickInterceptedException:
            print(f"Ad or overlay is blocking dropdown for {player_name}. Trying to remove it...")
            try:
                ad = driver.find_element(By.CSS_SELECTOR, "aside.AdSlot_centering__vHSRy")
                driver.execute_script("arguments[0].remove();", ad)
                time.sleep(0.5)
                dropdown.click()
            except Exception:
                print("Failed to remove overlay/ad.")

        # Get stats
        result = get_stats(driver, wait, player_name, stats_type)

        if result is None:
            print(f"No stats found for {player_name}")

    except Exception as e:
        print(f"Error scraping {player_name}: {e}")

    finally:
        driver.quit()

    return result

def get_player_facts(player_metadata):
    """
    Scrapes player's facts from their Elite Prospects page using Selenium.

    Parameters:
        player_metadata (pd.Series): Contains 'player_name' and 'link'.

    Returns:
        pd.DataFrame: Extracted player facts as a single-row DataFrame or empty DataFrame on failure.
    """
    player_name = str(player_metadata['player_name'])
    player_url = str(player_metadata['link'])

    print(f"Collecting facts for {player_name} at {player_url}")

    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = uc.Chrome(version_main=138, options=chrome_options)
    wait = WebDriverWait(driver, 15)

    result = None

    try:
        driver.get(player_url)
        time.sleep(random.uniform(1.5, 2.5))

        player_facts_section = wait.until(
            ec.presence_of_element_located((By.ID, "player-facts"))
        )

        facts_dict = {}

        # Main facts
        try:
            facts_list = player_facts_section.find_element(
                By.CLASS_NAME, "PlayerFacts_factsList__Xw_ID"
            )
            fact_items = facts_list.find_elements(By.TAG_NAME, "li")
            for item in fact_items:
                try:
                    label = item.find_element(By.CLASS_NAME, "PlayerFacts_factLabel__EqzO5").text.strip()
                    value = item.text.replace(label, "").strip()
                    facts_dict[label] = value
                except:
                    continue
        except:
            print("Failed to extract main facts.")

        # Extra facts
        try:
            extra_facts_list = player_facts_section.find_element(
                By.CSS_SELECTOR, ".PlayerFacts_factsList__Xw_ID.PlayerFacts_fullWidth__W878B"
            )
            extra_fact_items = extra_facts_list.find_elements(By.TAG_NAME, "li")
            for item in extra_fact_items:
                try:
                    label = item.find_element(By.CLASS_NAME, "PlayerFacts_factLabel__EqzO5").text.strip()
                    value = item.text.replace(label, "").strip()
                    facts_dict[label] = value

                    # Special handling for Draft
                    if label == "Drafted":
                        match = re.search(r"(\d{4}).*?round\s+(\d+).*?#(\d+)", value)
                        if match:
                            year, rnd, overall = match.groups()
                            facts_dict["Draft"] = f"{rnd}rd round, {overall}th overall ({year})"
                except:
                    continue
        except:
            print("No extra facts found.")

        # Height
        height_cm = None
        if "Height" in facts_dict:
            match = re.search(r"(\d+)\s*cm", facts_dict["Height"])
            if match:
                height_cm = int(match.group(1))

        # Weight
        weight_kg = None
        if "Weight" in facts_dict:
            match = re.search(r"(\d+)\s*kg", facts_dict["Weight"])
            if match:
                weight_kg = int(match.group(1))

        # Highlights
        highlights = []
        try:
            highlight_elements = player_facts_section.find_elements(By.CLASS_NAME, "highlights-tooltip")
            for elem in highlight_elements:
                tooltip = elem.get_attribute("data-tooltip-content")
                if tooltip:
                    highlights.append(tooltip.strip())
        except:
            print("Failed to extract highlights.")

        # Extract Player Types
        player_types = []
        try:
            player_types_container = player_facts_section.find_element(By.CLASS_NAME, "PlayerFacts_playerTypes__lGoC4")
            chip_elements = player_types_container.find_elements(By.CLASS_NAME, "Chip_chip__qIK6Z")
            for chip in chip_elements:
                text = chip.text.strip()
                if text:
                    player_types.append(text)
        except Exception as e:
            print("Failed to extract player types - No player types found.")
            player_types = None  # If failed, fallback to None

        description = None
        try:
            desc_elem = player_facts_section.find_element(By.CLASS_NAME, "PlayerFacts_description__ujmxU")
            full_desc = desc_elem.text.strip()
            description = re.split(r"\[EP \d{4}\]", full_desc)[0].strip()
        except:
            print("Description not found.")

        # Compile into a DataFrame
        result = pd.DataFrame([{
            "player_name": player_name,
            "nation": facts_dict.get("Nation"),
            "position": facts_dict.get("Position"),
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "shoots": facts_dict.get("Shoots"),
            "player_type": player_types,
            "nhl_rights": facts_dict.get("NHL Rights"),
            "draft": extract_draft_info(facts_dict.get("Draft")),
            "highlights": highlights,
            "description": truncate_description(description)
        }])

    except Exception as e:
        print(f"[ERROR] Failed to get facts for {player_name}: {e}")
        return pd.DataFrame()
    finally:
        driver.quit()

    return result

def get_player_facts_with_reusable_driver(player_metadata, driver, wait):
    player_name = str(player_metadata['player_name'])
    player_url = str(player_metadata['player_link_ep'])

    result = None
    try:
        print(f"Collecting facts for {player_name} at {player_url}")
        driver.get(player_url)

        # Wait for the page to load
        time.sleep(random.uniform(1.5, 5))
        player_facts_section = wait.until(
            ec.presence_of_element_located((By.ID, "player-facts"))
        )

        facts_dict = {}

        # Main facts
        try:
            print("Locating the main facts_list")
            facts_list = player_facts_section.find_element(
                By.CLASS_NAME, "PlayerFacts_factsList__Xw_ID"
            )
            fact_items = facts_list.find_elements(By.TAG_NAME, "li")
            print(f"Found {len(fact_items)} main facts")
            for item in fact_items:
                try:
                    label = item.find_element(By.CLASS_NAME, "PlayerFacts_factLabel__EqzO5").text.strip()
                    value = item.text.replace(label, "").strip()
                    facts_dict[label] = value
                except:
                    raise Exception(f"Failed to extract main fact: {item.text}")
        except:
            raise Exception("Failed to extract main facts.")

        # Extra facts
        try:
            print("Extracting extra facts...")
            extra_facts_list = player_facts_section.find_element(
                By.CSS_SELECTOR, ".PlayerFacts_factsList__Xw_ID.PlayerFacts_fullWidth__W878B"
            )
            extra_fact_items = extra_facts_list.find_elements(By.TAG_NAME, "li")
            for item in extra_fact_items:
                try:
                    label = item.find_element(By.CLASS_NAME, "PlayerFacts_factLabel__EqzO5").text.strip()
                    value = item.text.replace(label, "").strip()
                    facts_dict[label] = value

                    print(f"Extracted extra fact: {label}")

                    # Special handling for Draft
                    if label == "Drafted":
                        match = re.search(r"(\d{4}).*?round\s+(\d+).*?#(\d+)", value)
                        if match:
                            year, rnd, overall = match.groups()
                            facts_dict["Draft"] = f"{rnd}rd round, {overall}th overall ({year})"
                except:
                    raise Exception(f"Failed to extract extra fact: {item.text}")
        except Exception as e:
            raise Exception(f"Failed to extract extra facts: {e}")

        # Date of Birth
        date_of_birth = None
        if "Date of Birth" in facts_dict:
            date_of_birth = facts_dict["Date of Birth"]
            # Convert to datetime: example Oct 30, 1998
            date_of_birth = pd.to_datetime(date_of_birth, format='%b %d, %Y')

        # Height
        height_cm = None
        if "Height" in facts_dict:
            match = re.search(r"(\d+)\s*cm", facts_dict["Height"])
            if match:
                height_cm = int(match.group(1))

        # Weight
        weight_kg = None
        if "Weight" in facts_dict:
            match = re.search(r"(\d+)\s*kg", facts_dict["Weight"])
            if match:
                weight_kg = int(match.group(1))

        # Highlights
        highlights = []
        try:
            print("Extracting highlights...")
            highlight_elements = player_facts_section.find_elements(By.CLASS_NAME, "highlights-tooltip")
            for elem in highlight_elements:
                tooltip = elem.get_attribute("data-tooltip-content")
                if tooltip:
                    highlights.append(tooltip.strip())
            print("Successfully extracted highlights.")
        except:
            print("Failed to extract highlights.")

        # Extract Player Types
        player_types = []
        try:
            print("Extracting player types...")
            player_types_container = player_facts_section.find_element(By.CLASS_NAME, "PlayerFacts_playerTypes__lGoC4")
            chip_elements = player_types_container.find_elements(By.CLASS_NAME, "Chip_chip__qIK6Z")
            for chip in chip_elements:
                text = chip.text.strip()
                if text:
                    player_types.append(text)
            print("Successfully extracted player types.")
        except:
            player_types = None
            print("Failed to extract player types - No player types found.")

        description = None
        try:
            print("Extracting description...")
            desc_elem = player_facts_section.find_element(By.CLASS_NAME, "PlayerFacts_description__ujmxU")
            full_desc = desc_elem.text.strip()
            description = re.split(r"\[EP \d{4}\]", full_desc)[0].strip()
            print("Successfully extracted description.")
        except:
            print("Description not found.")

        # Compile into a DataFrame
        result = pd.DataFrame([{
            "player_name_ep": player_name,
            "player_link_ep": player_url,
            "date_of_birth": date_of_birth,
            "nation": facts_dict.get("Nation"),
            "position": facts_dict.get("Position"),
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "shoots": facts_dict.get("Shoots"),
            "player_type": player_types,
            "nhl_rights": facts_dict.get("NHL Rights"),
            "draft": extract_draft_info(facts_dict.get("Draft")),
            "highlights": highlights,
            "description": truncate_description(description)
        }])

    except Exception as e:
        raise Exception(f"[ERROR] Failed to get facts for {player_name}: {e}")

    return result

'''
    The following functions are used to handle the goalie's stats
'''