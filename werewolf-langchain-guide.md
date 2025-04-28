# Werewolf Multi-Agent Implementation with LangChain and Claude 3.5 Haiku

## Game Overview

Werewolf (also known as Mafia) is a social deduction game where players are secretly assigned roles and must work together or against each other to achieve their objectives. The game takes place in a fictional village plagued by werewolves who are hiding among the villagers.

### Game Objective

- **Villagers**: Identify and eliminate all werewolves
- **Werewolves**: Eliminate enough villagers to equal or outnumber them
- **Special Roles** (like the Seer): Help the villagers while remaining undetected by the werewolves

## Game Phases

The game alternates between two main phases:

### 1. Night Phase

- All players "close their eyes" (in our implementation, only certain agents are active)
- Werewolves "wake up" and silently choose a villager to eliminate
- The Seer "wakes up" and can investigate one player to determine if they're a werewolf
- Other special roles may take actions during this phase depending on the variant

### 2. Day Phase

- All players "open their eyes" and discover who was eliminated during the night
- Players discuss and debate to identify potential werewolves
- At the end of the day, players vote on who to "lynch" (eliminate)
- The player with the most votes is eliminated and their role is revealed
- The game checks if victory conditions have been met for either side

## Core Roles

### 1. Villager

- **Objective**: Identify and eliminate all werewolves
- **Abilities**: Can only vote during the day phase
- **Knowledge**: Knows only their own role
- **Strategy**: Must use deduction, observation, and discussion to identify werewolves

### 2. Werewolf

- **Objective**: Eliminate villagers until werewolves equal or outnumber them
- **Abilities**: Vote to eliminate one villager each night, plus vote during day phase
- **Knowledge**: Knows the identity of other werewolves
- **Strategy**: Must blend in with villagers during day phase while strategically eliminating key players at night

### 3. Seer

- **Objective**: Help villagers identify werewolves without being eliminated
- **Abilities**: Can check one player's role each night
- **Knowledge**: Gradually learns the true identity of other players
- **Strategy**: Must use this information without revealing their own identity to werewolves

## Implementation Requirements with LangChain Multi-Agent Framework

To implement Werewolf using LangChain and Claude 3.5 Haiku, Cursor should create a system with the following components:

### 1. Game Orchestrator

Create a central controller that:
- Maintains the game state (player roles, eliminated players, current phase)
- Enforces game rules and transitions between phases
- Processes actions from agents during appropriate phases
- Validates moves and determines when win conditions are met

### 2. Agent System

Each player should be represented by a Claude 3.5 Haiku agent that:
- Is assigned a specific role (villager, werewolf, or seer)
- Has appropriate role-specific instructions in its prompt
- Can only take actions permitted by its role and the current game phase
- Makes decisions based on available information

### 3. Communication Framework

Implement a communication system that:
- Enables public discussion during day phases
- Allows private communication among werewolves during night phases
- Provides private information to the seer
- Broadcasts game events (eliminations, phase changes)
- Prevents communication outside of authorized channels

### 4. Role-Specific Logic

For each role, implement:
- **Villager**: Ability to participate in day discussions and vote
- **Werewolf**: Ability to communicate with other werewolves at night and vote on elimination targets
- **Seer**: Ability to investigate one player per night and receive truthful information about their role

### 5. Game Flow Management

Implement a game loop that:
- Alternates between day and night phases
- Collects and processes votes during day phases
- Processes role-specific actions during night phases
- Checks win conditions after each phase
- Provides appropriate information to each agent based on their role

### 6. Information Control

Carefully manage what information each agent has access to:
- All agents should know who has been eliminated
- Werewolves should know the identity of other werewolves
- The seer should know the results of their investigations
- No agent should have access to information they wouldn't have in a real game

### 7. Decision Making

Enable agents to make decisions about:
- Who to vote for during day phases
- Who to eliminate (werewolves) or investigate (seer) during night phases
- What information to share or withhold during discussions

## Simplified Implementation Approach

For a basic implementation, Cursor should:

1. **Initialize the Game**:
   - Set up player agents with appropriate roles
   - Establish communication channels
   - Create the game state tracker

2. **Run Night Phase**:
   - Activate werewolf agents to select a target
   - Activate seer agent to investigate a player
   - Process night actions and update game state

3. **Run Day Phase**:
   - Inform all agents about elimination(s)
   - Facilitate a discussion round where each agent contributes
   - Collect votes from all agents
   - Eliminate the player with the most votes
   - Update game state

4. **Check Win Conditions**:
   - Villagers win if all werewolves are eliminated
   - Werewolves win if they equal or outnumber villagers

5. **Repeat** until a win condition is met

This simplified approach focuses on the core mechanics of Werewolf while leveraging LangChain's multi-agent capabilities and Claude 3.5 Haiku's reasoning abilities to create a functional implementation of the game.
