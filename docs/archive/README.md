# Match Masters — Board Analysis (Archive)

Language: Python

Tools: NumPy, OpenCV

Board analysis and strategy engine for the Match Masters puzzle game.

# General Description

This module analyses board states from Match Masters, a tile-matching puzzle game, and evaluates possible moves using a lookahead strategy engine.

# Game Rules

Match Masters is a game tile-matching puzzle video game, The goal is to clear tiles of the same color, potentially causing a chain reaction.

Each board is filled with the colors: Blue, Green, Yellow, Orange, Purple and Red.

Here is an example of a regular board from the game:

![Image of Game Board](https://github.com/Eden998/Match-Masters-Bot/blob/main/images/game_board.png)

# Algorithm

## 1. Image Recognition
The first thing the application does is to take a picture of the screen, after that it uses the OpenCV library to recognize shapes on the screen to make a replica of the game board in to a 2D array.

Here is an example for image recognition of a special tile from the game:

![Image of Game Board](https://github.com/Eden998/Match-Masters-Bot/blob/main/images/image_recognition.png)

## 2. Trying all possible moves
 The bot switches every 2 possible tiles, and sees if there is any match, if there is, it explodes all the matching tiles and simulates the drop of the tiles.

## 3. Recursion
After dropping the tiles due to a match, the same function is called again and checks if there is any chain reaction caused by the last move.

## 4. Finding the best move
The bot assigning a score to each move according to it's performence, and the best move is being kept and done at the end of the program.
