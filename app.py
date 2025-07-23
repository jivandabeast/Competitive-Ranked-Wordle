"""
Competitive Ranked Wordle
    A program to manage multi-player games of Wordle, processing scores, and calculating ELO rankings
Authors: Jivan RamjiSingh
Copyright (C) 2025  Jivan RamjiSingh

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

# ---
# Imports
# ---

import csv
import json
import jmespath
import yaml
import sqlite3
import logging
import re
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date
from fastapi import FastAPI
from pydantic import BaseModel
from openskill.models import PlackettLuce
from collections import defaultdict

# ---
# Database Operations
# ---

def load_db(config: dict):
    """
    Load sqlite3 db connection
    Inputs:
        config  obj     App configuration
    Outputs:
        db              DB connection
    """
    db = sqlite3.connect(config['database'])
    sq_cursor = db.cursor()

    # Check if the scores table is created, if not then make it
    try:
        sq_cursor.execute('SELECT * FROM scores LIMIT 5')
        logging.debug(f"{config['database']} table 'scores' exists.")
    except sqlite3.OperationalError:
        sq_cursor.execute("CREATE TABLE scores(id integer primary key autoincrement, player_email text, player_name text, puzzle integer, raw_score text, score integer, calculated_score integer, hard_mode integer, elo real, mu real, sigma real)")
        db.commit()
        logging.debug(f"{config['database']} table 'scores' created.")
    
    sq_cursor.close()
    return db

def update_entry(db: sqlite3.Connection, id: int, data: dict):
    """
    Update an entry in the db
    """
    db_cursor = db.cursor()
    new_fields = ""
    i = 1
    for k, v in data.items():
        if i == len(data):
            if (isinstance(v, int) or isinstance(v, float)):
                new_fields = f"{new_fields} {k} = {v}"
            else:
                new_fields = f"{new_fields} {k} = '{v}'"
        else:
            if (isinstance(v, int) or isinstance(v, float)):
                new_fields = f"{new_fields} {k} = {v},"
            else:
                new_fields = f"{new_fields} {k} = '{v}',"
        i += 1

    query_string = f"UPDATE scores SET{new_fields} WHERE id = {id}"
    db_cursor.execute(query_string)
    db_cursor.close()
    db.commit()
    logging.debug(f"Updated row in scores: {query_string}")

def add_entry(db: sqlite3.Connection, data: dict):
    """
    Add a wordle score entry to the db
    """
    db_cursor = db.cursor()
    cols = ""
    vals = ""
    i = 1
    for k, v in data.items():
        if i == len(data):
            if (isinstance(v, int) or isinstance(v, float)):
                cols = f"{cols} {k}"
                vals = f"{vals} {v}"
            else:
                cols = f"{cols} {k}"
                vals = f"{vals} '{v}'"
        else:
            if (isinstance(v, int) or isinstance(v, float)):
                cols = f"{cols} {k},"
                vals = f"{vals} {v},"
            else:
                cols = f"{cols} {k},"
                vals = f"{vals} '{v}',"
        i += 1

    query_string = f"INSERT INTO scores ({cols}) VALUES ({vals})"
    db_cursor.execute(query_string)
    db.commit()
    db_cursor.close()
    logging.debug(f"Added row in scores: {query_string}")

def get_entries(db: sqlite3.Connection, query_string):
    """
    Get rows for a given puzzle
    """
    db_cursor = db.cursor()
    db_cursor.execute(query_string)
    rows = db_cursor.fetchall()
    logging.debug(f"Sending query to DB: {query_string}")
    cols = [col[0] for col in db_cursor.description]
    data = [dict(zip(cols, row)) for row in rows]
    db_cursor.close()
    return data

# ---
# Data Definitions
# --

with open('config.yml', 'r') as f:
    config = yaml.safe_load(f)

model = PlackettLuce()

class Score(BaseModel):
    name: str
    score: str
    email: str

# ---
# Library Configurations
# ---

logging.basicConfig(filename='Output/out.log', level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
app = FastAPI()

db = load_db(config)

# ---
# Helper Functions
# ---

def get_wordle_puzzle(today):
    first_wordle = date(2021, 6, 19)
    delta = today - first_wordle
    return delta.days

def calculate_elo(player_a_elo, player_b_elo, result):
    pass

def calculate_openskill(puzzle: int = get_wordle_puzzle(date.today())):
    """
    Calculate Openskill rankings for a given day
    """
    query_string = f"SELECT * FROM scores WHERE puzzle = {puzzle}"
    entries = get_entries(db, query_string)
    
    players = []
    scores = []

    for entry in entries:
        query_string = f"SELECT sigma, mu FROM scores WHERE player_email = '{entry['player_email']}' AND sigma IS NOT NULL AND mu IS NOT NULL ORDER BY puzzle DESC LIMIT 1"
        player_data = get_entries(db, query_string)
        if player_data == []:
            players.append([model.rating(name=entry['player_email'])])
        else:
            player_data = player_data[0]
            players.append([model.rating(name=entry['player_email'], mu=player_data['mu'], sigma=player_data['sigma'])])
        scores.append(entry['calculated_score'])

    match_scores = model.rate(players, scores=scores)

    i = 0
    for entry in entries:
        player = match_scores[i][0]

        data = {
            'sigma': player.sigma,
            'mu': player.mu
        }

        update_entry(db, entry['id'], data)
        i += 1


def parse_score(score):
    """
    Parse a raw score submission for the puzzle and score, then generate calculated score
    """
    data = re.match(r'Wordle ([\d,]+) ([\dX])\/6(\*?)', score)
    puzzle = data.group(1)
    score = data.group(2)
    hard_mode = data.group(3)

    # Clean up the output
    puzzle = int(puzzle.replace(',', ''))

    if score == 'X':
        score = 7
    else:
        score = int(score)
    
    if hard_mode == '*':
        hard_mode = 1
    else:
        hard_mode = 0
    
    calculated_score = 7 - score

    data = {
        'puzzle': puzzle,
        'score': score,
        'calculated_score': calculated_score,
        'hard_mode': hard_mode
    }

    return data

def get_ELO_rankings():
    """
    Provide a ranking of all players in order of their ELO rank
    """
    pass

def get_daily_rankings():
    """
    Provide a ranking of all players based on their performance in a given puzzle
    """
    pass

def get_weekly_report():
    """
    Provide a weekly report of all players showing:
        - Beginning ELO
        - End ELO
        - Average score
    """
    pass

def elo_decay():
    """
    Degrade a players ELO on an unplayed day.
    Since players are not allowed to play on weekends or days off, this is going to require more logic on the client side
    """
    pass

# ---
# API Configuration
# ---

@app.post('/add_score/')
async def add_score(score: Score):
    """
    Add player score to DB
    """
    data = parse_score(score.score)
    data['player_email'] = score.email
    data['player_name'] = score.name
    data ['raw_score'] = score.score
    add_entry(db, data)
    return data

@app.get('/score/{email}')
async def get_score(email, puzzle: int = 0):
    return {"Player Email": email}

@app.get('/calculate_daily/')
async def calculate_daily():
    calculate_openskill()

@app.get('/daily_ranks/')
async def daily_ranks():
    pass

@app.get('/weekly_summary/')
async def weekly_summary():
    pass

def main():
    # print(config)
    db = load_db(config)  

    # add_entry(db, data)

    # update_entry(db, 1, data)

    # print(get_wordle_puzzle(date.today()))

    db.close()

# ---
# Entrypoint
# ---
if __name__ == '__main__':
    main()