"""
Competitive Ranked Wordle Helper Functions

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

import re
import math
from datetime import date

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

def get_wordle_puzzle(today):
    first_wordle = date(2021, 6, 19)
    delta = today - first_wordle
    return delta.days

def calculate_elo(player_a_elo, player_b_elo, result):
    # elo_change = 32 * (result -1 / (1 + 10 ** ((player_b_elo - player_a_elo) / 400)))
    prob = 1.0 / (1 + math.pow(10, (player_b_elo - player_a_elo) / 400.0))
    elo_change = 32 * (result - prob)
    return elo_change

def match_player_name(player_data: list, player_id: int = False, player_uuid: str = False):
    for player in player_data:
        if player_id:
            if player['player_id'] == player_id:
                return player['player_name']
        elif player_uuid:
            if player['player_uuid'] == player_uuid:
                return player['player_name']