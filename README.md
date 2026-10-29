# Match Masters Learning Helper

A desktop learning helper for Match Masters, designed to help you learn how to identify the best moves and understand why they work. It brings board state, move analysis, and match statistics into one PyQt5 interface so you can study move choices, follow-up sequences, and chain reactions.

> Intended for educational use and private matches with consenting participants. Please follow the game’s rules and terms of service.

## Features

- Real-time board display for following changes on the board
- Move analysis with configurable depth to compare possible outcomes
- Score and turn tracking across all game modes for reviewing match progress
- Booster status monitoring to help understand their role in a match
- Works with BlueStacks on Windows

### Full Game Demonstration

Watch a complete Match Masters game featuring the learning helper's move analysis, move selection, and gameplay tracking.

[**Watch the full game on YouTube**](https://www.youtube.com/watch?v=Fqvo3tljwD0)

## Demo

> Demo footage was recorded in Solo Challenge and private matches with a friend for testing and experimentation.

Finds the strongest move based on the current board and calculated follow-up sequences, as seen in the demo.

https://github.com/Sogli031/match-masters-bot/raw/main/demo.mp4

### Opening Move Planning

Watch the helper calculate a sequence of opening moves in Mutation Lab Solo Challenge, following extra moves and chain reactions with the game and analysis panel side by side.

https://github.com/Sogli031/match-masters-bot/raw/main/assets/demo_opening_moves.mp4

### Supersize Move Sequence

Follow a calculated sequence on an 8x8 Supersize board, with extra moves and UFO reactions shown alongside the helper.

https://github.com/Sogli031/match-masters-bot/raw/main/assets/demo_supersize_extended.mp4

### Extra Move Prediction

The analysis estimates when a move may grant an extra turn and explores follow-up sequences, helping you understand how chain reactions can affect the outcome.

https://github.com/Sogli031/match-masters-bot/raw/main/assets/demo_extra_move.mp4

### Disco Ball Move Analysis

A two-disco-ball sequence, with the game and helper panel shown side by side to follow the move analysis and resulting chain reactions.

https://github.com/Sogli031/match-masters-bot/raw/main/assets/demo_disco_prediction.mp4

## System Requirements

These are the project's setup requirements and recommended configuration; performance varies with the board size and lookahead settings.

| Component | Required | Recommended |
| --- | --- | --- |
| Operating system | 64-bit Windows 10 or 11 | 64-bit Windows 11 |
| Memory | 8 GB RAM (enforced by setup) | 16 GB RAM or more |
| Processor | 64-bit CPU with hardware virtualization | 4 CPU cores or more |
| Virtualization | Intel VT-x or AMD-V/SVM enabled in BIOS/UEFI | Enabled |
| Storage | Space for BlueStacks, its Android instance, the game and helper files | SSD with room for updates and diagnostic logs |

### Software

- BlueStacks 5 with an Android 9 Pie64 instance. The bundled setup targets version **5.22.262.1002**; compatibility with other versions is not verified.
- Python 3.11 for running from source, with packages from `requirements.txt`.
- Administrator access for emulator setup.

On an 8 GB PC, start with the lighter lookahead presets. Higher lookahead settings and 8x8 boards require more processing time.

## Getting Started

1. Install dependencies: `pip install -r requirements.txt`
2. Launch the app

---

*Built for learning, experimenting, and exploring game mechanics. Questions? DM me on Discord: **sogli031**.*
