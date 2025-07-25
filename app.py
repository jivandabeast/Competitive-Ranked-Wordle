"""
Competitive Ranked Wordle
    A program to manage multi-player games of Wordle, processing scores, and calculating ELO rankings

Authors: Jivan RamjiSingh

TODO:
    - Add msteams adaptive card for the EOD roundup
    - Set margin parameter for PlackettLuce model to account for match skill
    - Lots of documentation
    - Add ELO and OpenSkill decay (pending rate determination)

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

import os
import json
import yaml
import sqlite3
import logging
import re
import math
import jwt
from typing import Annotated
from collections import defaultdict
from datetime import date, timedelta, timezone, datetime
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext
from pydantic import BaseModel
from pydantic import BaseModel
from openskill.models import PlackettLuce

# ---
# Database Operations
# ---

def check_db(config: dict):
    """
    Load sqlite3 db connection
    Inputs:
        config  obj     App configuration
    Outputs:
        db              DB connection
    """
    try:
        with sqlite3.connect(config['database']) as db:
            sq_cursor = db.cursor()

            # Check if the scores table is created, if not then make it
            try:
                sq_cursor.execute('SELECT * FROM scores LIMIT 5')
                logging.debug(f"{config['database']} table 'scores' exists.")
            except sqlite3.OperationalError:
                sq_cursor.execute("CREATE TABLE scores(id integer primary key autoincrement, player_email text, player_name text, puzzle integer, raw_score text, score integer, calculated_score integer, hard_mode integer, elo real, mu real, sigma real, ordinal real, elo_delta real, ordinal_delta real)")
                db.commit()
                logging.debug(f"{config['database']} table 'scores' created.")
            
            sq_cursor.close()
            return True
    except:
        return False

def update_entry(id: int, data: dict):
    """
    Update an entry in the db
    """
    with sqlite3.connect(config['database']) as db:
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

def add_entry(data: dict):
    """
    Add a wordle score entry to the db
    """
    with sqlite3.connect(config['database']) as db:
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

def get_entries(query_string: str):
    """
    Get rows for a given puzzle
    """
    with sqlite3.connect(config['database']) as db:
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

config_file = os.getenv('CONFIG_FILE', 'config.yml')
with open(config_file, 'r') as f:
    config = yaml.safe_load(f)

model = PlackettLuce()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

SECRET_KEY: str = config['security']['secret_key']
ALGORITHM: str = config['security']['algorithm']
ACCESS_TOKEN_EXPIRE_MINUTES: str = config['security']['token_expiration']
USERS: str = config['security']['users']

class Score(BaseModel):
    name: str
    score: str
    email: str

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class User(BaseModel):
    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool | None = None


class UserInDB(User):
    hashed_password: str

# ---
# Library Configurations
# ---

logging.basicConfig(filename=config['log_file'], level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
app = FastAPI()
if check_db(config):
    pass
else:
    raise(TypeError("DB Failed to Init Properly"))

# ---
# Helper Functions
# ---

def check_players(start: int, end: int, hard_mode: bool = True):
    """
    Checks if anyone played a given puzzle
    """
    if hard_mode:
        query_string = f"SELECT * FROM scores WHERE puzzle >= {start} and puzzle <= {end} AND hard_mode = 1"
    else:
        query_string = f"SELECT * FROM scores WHERE puzzle >= {start} and puzzle <= {end}"

    entries = get_entries(query_string)
    if entries == []:
        return False
    else:
        return True

def get_wordle_puzzle(today):
    first_wordle = date(2021, 6, 19)
    delta = today - first_wordle
    return delta.days

def calculate_elo(player_a_elo, player_b_elo, result):
    # elo_change = 32 * (result -1 / (1 + 10 ** ((player_b_elo - player_a_elo) / 400)))
    prob = 1.0 / (1 + math.pow(10, (player_b_elo - player_a_elo) / 400.0))
    elo_change = 32 * (result - prob)
    return elo_change

def calculate_openskill(puzzle: int):
    """
    Calculate Openskill rankings for a given day
    """
    query_string = f"SELECT * FROM scores WHERE puzzle = {puzzle} AND hard_mode = 1"
    entries = get_entries(query_string)
    if len(entries) == 1:
        # Don't do calculations when only one player submits
        for entry in entries:
            data = {
                'sigma': entry['sigma'],
                'mu': entry['mu'],
                'ordinal': entry['ordinal'],
                'ordinal_delta': entry['ordinal_delta'],
            }
        return False
    
    players = []
    scores = []
    ords = {}

    for entry in entries:
        query_string = f"SELECT mu, sigma, ordinal FROM scores WHERE player_email = '{entry['player_email']}' AND sigma IS NOT NULL AND mu IS NOT NULL ORDER BY puzzle DESC LIMIT 1"
        player_data = get_entries(query_string)
        if player_data == []:
            players.append([model.rating(name=entry['player_email'])])
            ords[entry['player_email']] = 0
        else:
            player_data = player_data[0]
            players.append([model.rating(name=entry['player_email'], mu=player_data['mu'], sigma=player_data['sigma'])])
            ords[entry['player_email']] = player_data['ordinal']
        scores.append(entry['calculated_score'])

    match_scores = model.rate(players, scores=scores)

    i = 0
    for entry in entries:
        player = match_scores[i][0]

        data = {
            'sigma': player.sigma,
            'mu': player.mu,
            'ordinal': player.ordinal(),
            'ordinal_delta': ords[entry['player_email']] - player.ordinal()
        }

        update_entry(entry['id'], data)
        i += 1

def get_player_elos(players: list):
    query_string = "SELECT DISTINCT player_email FROM scores"
    entries = get_entries(query_string)
    ratings = {}
    for player in entries:
        if player['player_email'] in players:
            query_string = f"SELECT elo, puzzle FROM scores WHERE player_email = '{player['player_email']}' AND elo NOT NULL ORDER BY puzzle DESC LIMIT 1"
            elo = get_entries(query_string)
            if elo == []:
                ratings[player['player_email']] = 400
            else:
                ratings[player['player_email']] = elo[0]['elo']
    return ratings

def calculate_match_elo(puzzle: int):
    """
    Legacy ELO Calculation
    Translate rankings into 1-1 matches between each player, then sum the elo change
    """
    query_string = f"SELECT * FROM scores WHERE puzzle = {puzzle} AND hard_mode = 1"
    entries = get_entries(query_string)
    if len(entries) == 1:
        # Don't do calculations when only one player submits
        for entry in entries:
            data = {
                'elo': entry['elo'],
                'elo_delta': entry['elo_delta'],
            }
        return False
    # ranked_players = sorted(entries, key=lambda x: x['calculated_score'], reverse=True)
    
    player_emails = []
    grouped = {i: [] for i in range(7)}  # Initialize keys 0 through 6
    for entry in entries:
        score = entry.get('calculated_score')
        grouped[score].append(entry)
        player_emails.append(entry['player_email'])

    current_ratings = get_player_elos(player_emails)

    for player in entries:
        overall_change = 0
        for i in range(7):
            if player['calculated_score'] > i:
                # win condition
                for opp in grouped[i]:
                    change = calculate_elo(current_ratings[player['player_email']], current_ratings[opp['player_email']], 1)
                    overall_change += change
            elif player['calculated_score'] == i:
                # draw condition
                for opp in grouped[i]:
                    if player == opp:
                        # Player is included in this, do not calculate against themselves
                        continue
                    change = calculate_elo(current_ratings[player['player_email']], current_ratings[opp['player_email']], 0.5)
                    overall_change += change
            else:
                # loss condition
                for opp in grouped[i]:
                    change = calculate_elo(current_ratings[player['player_email']], current_ratings[opp['player_email']], 0)
                    overall_change += change
        data = {
            'elo': current_ratings[player['player_email']] + overall_change,
            'elo_delta': overall_change
        }
        update_entry(player['id'], data)
        
def blame(email: str, puzzle: int):
    """
    Legacy ELO Calculation
    Translate rankings into 1-1 matches between each player, then sum the elo change
    """
    query_string = f"SELECT * FROM scores WHERE puzzle = {puzzle} AND hard_mode = 1"
    entries = get_entries(query_string)
    entries = sorted(entries, key=lambda x: x['calculated_score'], reverse=True)
    
    player_emails = []
    grouped = {i: [] for i in range(7)}  # Initialize keys 0 through 6
    for entry in entries:
        score = entry.get('calculated_score')
        grouped[score].append(entry)
        player_emails.append(entry['player_email'])

    current_ratings = get_player_elos(player_emails)

    output_string = ""
    for player in entries:
        if player['player_email'] == email:
            output_string = f"{output_string}Analysis of {player['player_name']}'s Performance in Wordle #{puzzle}:"
            output_string = f"{output_string}\n\n{player['player_name']} started with an ELO of {current_ratings[player['player_email']]}"
            overall_change = 0
            for i in range(7):
                if player['calculated_score'] > i:
                    # win condition
                    for opp in grouped[i]:
                        change = calculate_elo(current_ratings[player['player_email']], current_ratings[opp['player_email']], 1)
                        overall_change += change
                        output_string = f"{output_string}\n\tWon against {opp['player_name']}. ELO Change: {change}"
                elif player['calculated_score'] == i:
                    # draw condition
                    for opp in grouped[i]:
                        if player == opp:
                            # Player is included in this, do not calculate against themselves
                            continue
                        change = calculate_elo(current_ratings[player['player_email']], current_ratings[opp['player_email']], 0.5)
                        overall_change += change
                        output_string = f"{output_string}\n\tTied against {opp['player_name']}. ELO Change: {change}"
                else:
                    # loss condition
                    for opp in grouped[i]:
                        # print(f"{player['player_name']}:{player['calculated_score']} loss {opp['player_name']}:{opp['calculated_score']} change {calculate_elo(current_ratings[player['player_email']], current_ratings[opp['player_email']], 0)}")
                        change = calculate_elo(current_ratings[player['player_email']], current_ratings[opp['player_email']], 0)
                        overall_change += change
                        output_string = f"{output_string}\n\tLost against {opp['player_name']}. ELO Change: {change}"
            output_string = f"{output_string}\n\nIn total {player['player_name']}'s ELO changed by {overall_change}, bringing their new ELO rating to: {current_ratings[player['player_email']] + overall_change}"
    if output_string == "":
        output_string = f"{email} did not play Wordle today!"
    return output_string

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

def get_daily_ranks(puzzle: int):
    query_string = f"SELECT player_name, hard_mode, calculated_score FROM scores WHERE puzzle = {puzzle}"
    data = get_entries(query_string)
    for result in data:
        result['hard_mode'] = 'Y' if result['hard_mode'] == 1 else 'N'
    sorted_players = sorted(data, key=lambda x: x['calculated_score'], reverse=True)
    player_chart = '| Player | Hard Mode | Ranking |\n| --- | --- | --- |'
    i = 1
    for player in sorted_players:
        player_chart = f"{player_chart}\n| {player['player_name']} | {player['hard_mode']} | {i} |"
        player['rank'] = i
        i += 1
    print(player_chart)

    output = {
        'raw_data': sorted_players,
        'md_chart': player_chart
    }
    return output

def get_daily_report(today: date):
    """
    Provide a ranking of all players in order of their OpenSkill rank
    """
    puzzle = get_wordle_puzzle(today - timedelta(days=1))
    players = defaultdict(list)
    player_stats = {}

    query_string = f"SELECT player_name, player_email, elo, mu, sigma, puzzle, score, ordinal, ordinal_delta, elo_delta FROM scores WHERE puzzle = {puzzle}"
    entries = get_entries(query_string)
    for entry in entries:
        players[entry['player_name']].append(entry)
    
    players = dict(players)
    for player, scores in players.items():
        player_stats[player] = {}

        for score in scores:
            player_stats[player]['end_elo'] = round(score['elo'], 3)
            player_stats[player]['elo_change'] = round(score['elo_delta'], 3)

            player_stats[player]['end_ord'] = round(score['ordinal'], 5)
            player_stats[player]['ord_change'] = round(score['ordinal_delta'], 5)
    
    # sort player_stats by end ordinal
    sorted_keys = sorted(player_stats, key=lambda k: player_stats[k]['end_ord'], reverse=True)
    sorted_player_stats = {}
    for key in sorted_keys:
        sorted_player_stats[key] = player_stats[key]

    with open(config['adaptive_card'], 'r') as f:
        adaptive_card = json.load(f)

    adaptive_card['body'][0]['inlines'][0]['text'] = f"{today.isoformat()}: Wordle Report"
    cols = 3
    headers = ['Wordler', 'ELO', 'OpenSkill']

    for i in range(cols):
        col = {
            "width": 1
        }
        adaptive_card['body'][1]['columns'].append(col)
    
    header_row = {
        "type": "TableRow",
        "cells": []
    }
    for header in headers:
        cell = {
            "type": "TableCell",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": header,
                        "wrap": True
                    }
                ]
        }
        header_row['cells'].append(cell)

    adaptive_card['body'][1]['rows'].append(header_row)

    rows = []
    for player, stats in sorted_player_stats.items():
        row = {
            "type": "TableRow",
            "cells": [
                {
                    "type": "TableCell",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": player,
                                "wrap": True
                            }
                        ]
                },
                {
                    "type": "TableCell",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"{stats['end_elo']}\n\nΔ {stats['elo_change']}",
                                "wrap": True
                            }
                        ]
                },
                {
                    "type": "TableCell",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"{stats['end_ord']}\n\nΔ {stats['ord_change']}",
                                "wrap": True
                            }
                        ]
                }
            ]
        }
        rows.append(row)
    adaptive_card['body'][1]['rows'].extend(rows)
    output = {
        'adaptive_card': adaptive_card,
        'player_stats': player_stats,
        'sorted_player_stats': sorted_player_stats
    }
    return output

def get_weekly_report(end_date: date):
    """
    Provide a weekly report of all players showing:
        - Beginning ELO
        - End ELO
        - Average score
    """
    start_date = end_date - timedelta(days=7)
    end = get_wordle_puzzle(end_date)
    start = get_wordle_puzzle(start_date)
    players = defaultdict(list)
    player_stats = {}

    query_string = f"SELECT player_name, player_email, elo, mu, sigma, puzzle, score FROM scores WHERE puzzle >= {start} and puzzle <= {end}"
    entries = get_entries(query_string)
    for entry in entries:
        players[entry['player_name']].append(entry)
    
    players = dict(players)
    for player, scores in players.items():
        # all_scores = list(map(lambda s: s['score'], scores))
        player_stats[player] = {}

        all_scores = []
        earliest = end + 1
        latest = 0
        for score in scores:
            all_scores.append(score['score'])
            if score['puzzle'] > latest:
                player_stats[player]['end_elo'] = round(score['elo'], 3)
                player_stats[player]['end_ord'] = round(model.rating(mu=score['mu'], sigma=score['sigma']).ordinal(), 5)
                latest = score['puzzle']
            if score['puzzle'] < earliest:
                player_stats[player]['start_elo'] = round(score['elo'], 3)
                player_stats[player]['start_ord'] = round(model.rating(mu=score['mu'], sigma=score['sigma']).ordinal(), 5)
                earliest = score['puzzle']
        player_stats[player]['average_score'] = round(sum(all_scores) / len(all_scores), 1)
        player_stats[player]['elo_change'] = round(player_stats[player]['end_elo'] - player_stats[player]['start_elo'], 3)
        player_stats[player]['ord_change'] = round(player_stats[player]['end_ord'] - player_stats[player]['start_ord'], 3)
    
    # sort player_stats by end ordinal
    sorted_keys = sorted(player_stats, key=lambda k: player_stats[k]['end_ord'], reverse=True)
    sorted_player_stats = {}
    for key in sorted_keys:
        sorted_player_stats[key] = player_stats[key]

    with open(config['adaptive_card'], 'r') as f:
        adaptive_card = json.load(f)

    adaptive_card['body'][0]['inlines'][0]['text'] = 'Wordle Overall Standings'
    cols = 4
    headers = ['Wordler', 'ELO', 'OpenSkill', 'Average Attempts']

    for i in range(cols):
        col = {
            "width": 1
        }
        adaptive_card['body'][1]['columns'].append(col)
    
    header_row = {
        "type": "TableRow",
        "cells": []
    }
    for header in headers:
        cell = {
            "type": "TableCell",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": header,
                        "wrap": True
                    }
                ]
        }
        header_row['cells'].append(cell)

    adaptive_card['body'][1]['rows'].append(header_row)

    rows = []
    for player, stats in sorted_player_stats.items():
        row = {
            "type": "TableRow",
            "cells": [
                {
                    "type": "TableCell",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": player,
                                "wrap": True
                            }
                        ]
                },
                {
                    "type": "TableCell",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"{round(stats['end_elo'], 2)}\n\nΔ {stats['elo_change']}",
                                "wrap": True
                            }
                        ]
                },
                {
                    "type": "TableCell",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"{round(stats['end_ord'], 2)}\n\nΔ {stats['ord_change']}",
                                "wrap": True
                            }
                        ]
                },
                {
                    "type": "TableCell",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": str(stats['average_score']),
                                "wrap": True
                            }
                        ]
                }
            ]
        }
        rows.append(row)
    adaptive_card['body'][1]['rows'].extend(rows)
    output = {
        'adaptive_card': adaptive_card,
        'player_stats': player_stats,
        'sorted_player_stats': sorted_player_stats
    }
    return output

def elo_decay():
    """
    Degrade a players ELO on an unplayed day.
    Since players are not allowed to play on weekends or days off, this is going to require more logic on the client side
    """
    pass

# ---
# FastAPI Security Functions
# ---

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)


def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise credentials_exception
    user = get_user(USERS, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# ---
# API Configuration
# ---

@app.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    user = authenticate_user(USERS, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")

@app.post('/add_score/')
async def add_score(score: Score, current_user: Annotated[User, Depends(get_current_active_user)]):
    """
    Add player score to DB
    """
    data = parse_score(score.score)
    data['player_email'] = score.email
    data['player_name'] = score.name
    data ['raw_score'] = score.score
    add_entry(data)
    return data

@app.get('/score/{email}')
async def get_score(email, current_user: Annotated[User, Depends(get_current_active_user)], puzzle: int = get_wordle_puzzle(date.today())):
    query_string = f"SELECT puzzle, score, calculated_score, elo, mu, sigma FROM scores WHERE puzzle = {puzzle} AND player_email = '{email}'"
    data = get_entries(query_string)
    if data == []:
        return {'status': 404, 'msg': f'{email} did not played today :('}
    else:
        return data[0]

@app.get('/blame/{email}')
async def blame_score(email, current_user: Annotated[User, Depends(get_current_active_user)], puzzle: int = get_wordle_puzzle(date.today()) - 1):
    msg = blame(email, puzzle)
    return {'msg': msg}

@app.get('/calculate_daily/')
async def calculate_daily(current_user: Annotated[User, Depends(get_current_active_user)], puzzle: int = get_wordle_puzzle(date.today())):
    if check_players(puzzle, puzzle, True):
        calculate_openskill(puzzle)
        calculate_match_elo(puzzle)
    else:
        pass
    return {'status': 200}

@app.get('/daily_ranks/')
async def daily_ranks(current_user: Annotated[User, Depends(get_current_active_user)], puzzle: int = get_wordle_puzzle(date.today())):
    """
    Provide a ranking of all players based on their performance (rank only, hard mode independent) in a given puzzle
    """
    if check_players(puzzle, puzzle, False):
        output = get_daily_ranks(puzzle)
    else:
        output = {'status': 404, 'msg': 'Nobody played today :('}
    return output

@app.get('/daily_summary/')
async def daily_summary(current_user: Annotated[User, Depends(get_current_active_user)], report_date: date = date.today()):
    puzzle = get_wordle_puzzle(report_date - timedelta(days=1))
    if check_players(puzzle, puzzle, False):
        data = get_daily_report(report_date)
    else:
        data = {'status': 404, 'msg': 'Nobody played today :('}
    return data

@app.get('/weekly_summary/')
async def weekly_summary(current_user: Annotated[User, Depends(get_current_active_user)], end_date: date = date.today()):
    start_date = end_date - timedelta(days=7)
    end = get_wordle_puzzle(end_date)
    start = get_wordle_puzzle(start_date)

    if check_players(start, end, False):
        data = get_weekly_report(end_date)
    else:
        data = {'status': 404, 'msg': 'Nobody played today :('}
    return jsonable_encoder(data)