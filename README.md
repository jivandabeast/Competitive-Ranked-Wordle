# Competitive Ranked Wordle

Backend API based server for handling competitive multiplayer games of Wordle.

## Features

- Handles score parsing
- Generates a daily ranking of players (hard mode non-exclusive)
- Calculates multiplayer ELO and OpenSkill ratings for each player (hard mode exclusive)
- Generates a daily report of ELO and OpenSkill ratings (sorted by OpenSkill ordinal)
- Generates a weekly report of ELO and OpenSkill ratings (sorted by OpenSkill ordinal)
- Ability to "blame" your ELO changes on other players (provides a detailed output of matchups against other players and ELO lost/gained)

## Setup

### Docker

1. Pull the git repository

   `git clone https://github.com/jivandabeast/Competitive-Ranked-Wordle.git`

2. Build the Docker image

   `cd Competitive-Ranked-Wordle`

   `docker build -t competitive-ranked-wordle .`

3. Create a folder for the resources & create required files

   ```
   $ mkdir /docker/competitive-ranked-wordle

   $ mkdir /docker/competitive-ranked-wordle/Output

   $ cd /docker/competitive-ranked-wordle

   $ wget https://raw.githubusercontent.com/jivandabeast/Competitive-Ranked-Wordle/refs/heads/master/config.sample.yml

   $ touch wordle.db

   $ touch Output/out.log

   $ mv config.sample.yml config.yml

   ```

4. Edit `config.yml`, following the prompts in the file

5. Execute the docker image

   `docker run -d --name competitive-ranked-wordle -v /docker/competitive-ranked-wordle:/data -e CONFIG_FILE=/data/config.yml -p 8080:80 competitive-ranked-wordle`

6. Open the Web-UI being hosted on Port 8080
