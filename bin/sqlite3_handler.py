
"""
Competitive Ranked Wordle Sqlite3 Database Handler

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

import sqlite3
import logging

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

def update_entry(config: dict, id: int, data: dict):
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

def add_entry(config: dict, data: dict):
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

def get_entries(config: dict, query_string: str):
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