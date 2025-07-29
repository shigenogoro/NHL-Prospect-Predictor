"""
    API for Official NHL Scraper
    1. get_player_by_team(team, season): Allows you to get all players from a specific team and season
    2. get_player_stats(player_metadata): Allows you to get all information from a player's webpage
"""
from io import StringIO

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

"""
    The following section is global variables
"""
valid_teams = [
        "bruins", "sabres", "redwings", "panthers", "canadiens",
        "senators", "lightning", "mapleleafs", "hurricanes", "bluejackets",
        "devils", "islanders", "rangers", "flyers", "penguins",
        "capitals", "blackhawks", "avalanche", "stars", "wild",
        "predators", "blues", "jets", "ducks", "flames",
        "oilers", "kings", "sharks", "kraken", "canucks",
        "goldenknights", "utah"
    ]

"""
    The following section is helper functions
"""
def print_team_links(season):
    valid_teams = [
        "bruins", "sabres", "redwings", "panthers", "canadiens",
        "senators", "lightning", "mapleleafs", "hurricanes", "bluejackets",
        "devils", "islanders", "rangers", "flyers", "penguins",
        "capitals", "blackhawks", "avalanche", "stars", "wild",
        "predators", "blues", "jets", "ducks", "flames",
        "oilers", "kings", "sharks", "kraken", "canucks",
        "goldenknights", "utah"
    ]

    # Get the season start year and season end year
    season_year = season.split("-")
    season_start_year = season_year[0]
    season_end_year = season_year[1]
    season_year_cat = season_start_year + season_end_year

    for i, team in enumerate(valid_teams):
        # print divider after 5 teams
        if valid_teams.index(team) % 5 == 0:
            print("----------------------------------------------------------------")
        print(f"{i}: https://www.nhl.com/{team}/stats/{season_year_cat}")

def validate_team(team):
    if team not in valid_teams:
        return False

    return True

def validate_season(season):
    # if season is not in YYYY-YYYY format, return False
    if not re.match(r'^\d{4}-\d{4}$', season):
        return False
    return True

"""
    The following section is APIs to get data from official NHL website
"""
def get_player_by_team(team, season):
    """
        Get all players from a specific team and season
        Parameters:
            team (str): Name of the team
            season (str): Name of the season
        Returns:
            df (pd.DataFrame): DataFrame with all players
    """
    # Validate the team name
    if not validate_team(team):
        raise ValueError(f"Invalid team. Valid teams are: {', '.join(valid_teams)}")

    # Validate the season format
    if not validate_season(season):
        raise ValueError("Invalid season format. Please use the format 'YYYY-YYYY'")

    # Get the season start year and season end year
    season_year = season.split("-")
    season_start_year = season_year[0]
    season_end_year = season_year[1]
    season_year_cat = season_start_year + season_end_year

    # Skip Lockout Season
    if season == "2004-2005":
        print(f"Skipping {season} due to lockout.")
        return None

    # Get the URL
    url = f"https://www.nhl.com/{team}/stats/{season_year_cat}"

    # Set up Selenium Chrome Driver
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = uc.Chrome(version_main=138, options=chrome_options)
    wait = WebDriverWait(driver, 15)

    # Get the page
    driver.get(url)

    # Initiate a list of players
    players = []

    try:
        # Collecting Data from {team} in {season}
        print(f"Collecting data from {url}")

        # Wait for the table to load
        wait.until(ec.presence_of_element_located((By.CSS_SELECTOR, "table.rt-table")))

        # Slight pause to ensure all data is loaded
        time.sleep(2)

        # Locate the players' link elements
        player_link_elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/player/']")

        # Locate each row with player info
        rows = driver.find_elements(By.CSS_SELECTOR, "tbody.rt-tbody > tr.rt-tr")
        for row in rows:
            try:
                name_elem = row.find_element(By.CSS_SELECTOR, "a[href*='/player/']")
                player_name = name_elem.text.strip()
                player_link = name_elem.get_attribute("href")

                image_url = None
                try:
                    # Try <img>
                    img_elem = row.find_element(By.CSS_SELECTOR, ".headshot-container img")
                    image_url = img_elem.get_attribute("src")
                except:
                    try:
                        # Try <image> (SVG)
                        svg_elem = row.find_element(By.CSS_SELECTOR, ".headshot-container image")
                        image_url = svg_elem.get_attribute("xlink:href") or svg_elem.get_attribute("href")
                    except:
                        # No image found
                        print(f"No image found for {player_name}")

                    # Extract position
                    try:
                        pos_elem = row.find_element(By.CSS_SELECTOR, "td span[aria-label]")
                        player_pos = pos_elem.text.strip()
                    except:
                        player_pos = "G"
                        print(f"{player_name} is a goalie.")

                    players.append({
                        "player_name": player_name,
                        "player_pos": player_pos,
                        "player_link": player_link,
                        "player_image": image_url
                    })

            except Exception as inner_e:
                print("Skipping row due to error:", inner_e)
                continue

    except Exception as e:
        print(f"Failed to scrape {team} for {season} at {url}")
        print("Error:", e)

    except:
        print(f"Failed to scrape {team} for {season} at {url}")
    finally:
        driver.quit()

    # Convert to dataframe
    players_metadata = pd.DataFrame(players)
    return players_metadata

def get_player_by_team_with_reusable_driver(team, season, driver, wait):
    """
    Get all players from a specific team and season using a provided Selenium driver.

    Parameters:
        team (str): Name of the team
        season (str): Season in 'YYYY-YYYY' format
        driver (webdriver.Chrome): A reusable undetected_chromedriver instance
        wait (WebDriverWait): WebDriverWait instance for the driver

    Returns:
        pd.DataFrame: DataFrame with players' names and NHL profile links
    """
    # Validate the team name
    if not validate_team(team):
        raise ValueError(f"Invalid team. Valid teams are: {', '.join(valid_teams)}")

    # Validate the season format
    if not validate_season(season):
        raise ValueError("Invalid season format. Please use the format 'YYYY-YYYY'")

    if season == "2004-2005":
        print(f"Skipping {season} due to lockout.")
        return None

    # Format the URL
    season_year_cat = season.replace("-", "")
    url = f"https://www.nhl.com/{team}/stats/{season_year_cat}"

    players = []
    try:
        print(f"Collecting data from {url}")
        driver.get(url)
        wait.until(ec.presence_of_element_located((By.CSS_SELECTOR, "table.rt-table")))
        time.sleep(2)

        # Locate each row with player info
        rows = driver.find_elements(By.CSS_SELECTOR, "tbody.rt-tbody > tr.rt-tr")
        for row in rows:
            try:
                name_elem = row.find_element(By.CSS_SELECTOR, "a[href*='/player/']")
                player_name = name_elem.text.strip()
                player_link = name_elem.get_attribute("href")

                image_url = None
                try:
                    # Try <img>
                    img_elem = row.find_element(By.CSS_SELECTOR, ".headshot-container img")
                    image_url = img_elem.get_attribute("src")
                except:
                    try:
                        # Try <image> (SVG)
                        svg_elem = row.find_element(By.CSS_SELECTOR, ".headshot-container image")
                        image_url = svg_elem.get_attribute("xlink:href") or svg_elem.get_attribute("href")
                    except:
                        # No image found
                        print(f"No image found for {player_name}")

                # Extract position
                try:
                    pos_elem = row.find_element(By.CSS_SELECTOR, "td span[aria-label]")
                    player_pos = pos_elem.text.strip()
                except:
                    player_pos = "G"
                    print(f"{player_name} is a goalie.")

                players.append({
                    "player_name": player_name,
                    "player_pos": player_pos,
                    "player_link": player_link,
                    "player_image": image_url
                })

            except Exception as inner_e:
                print("Skipping row due to error:", inner_e)
                continue

    except Exception as e:
        print(f"Failed to scrape {team} for {season} at {url}")
        print("Error:", e)
        return None

    return pd.DataFrame(players)


def get_player_stats_with_reusable_driver(player_metadata, driver, wait):
    """
    Get a player's regular season and playoff stats from their NHL player page.

    Parameters:
        player_metadata (pd.Series): Series with 'player_name' and 'player_link_official'
        driver (webdriver): Reusable Selenium driver
        wait (WebDriverWait): Reusable WebDriverWait object

    Returns:
        pd.DataFrame: Combined DataFrame with regular and playoff stats
    """

    player_url = player_metadata['player_link_official']
    player_name = player_metadata['player_name']
    df_regular, df_playoffs = None, None

    try:
        print(f"Collecting {player_name}'s stats from {player_url}")
        driver.get(player_url)
        time.sleep(random.uniform(1.5, 2.5))

        # ---------- Step 1: Select All Leagues and Scrape Regular Season ----------
        try:
            league_dropdown = wait.until(ec.element_to_be_clickable(
                (By.XPATH, "//input[@id='league-select']/following-sibling::div//button")
            ))

            print("Successfully located dropdown button")

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", league_dropdown)
            driver.execute_script("arguments[0].click();", league_dropdown)

            print("Successfully clicked dropdown button")

            time.sleep(1)

            all_leagues_option = wait.until(ec.element_to_be_clickable(
                (By.XPATH, "//li[normalize-space()='All Leagues']")
            ))

            print("Successfully located all leagues option")

            all_leagues_option.click()

            print("Successfully clicked all leagues option")

            time.sleep(2)

            # Scrape the table
            soup = BeautifulSoup(driver.page_source, "html.parser")
            table = soup.find("table", id="career-stats-table")

            # print(table.prettify()[:500])

            if not table:
                raise ValueError("No regular season stats tables found on page")

            # Convert table to dataframe
            html_str = str(table)
            df_regular = pd.read_html(StringIO(html_str))[0]

            # Add player name to the dataframe
            df_regular.insert(0, "Player", player_name)

            print("Successfully scraped regular season stats")

            return df_regular

        except Exception as e:
            print(f"Failed to scrape regular season for {player_name}: {e}")

    except Exception as e:
        print(f"Failed to scrape {player_name} at {player_url}")
        print("Error:", e)
        return None



