import React, { useReducer, useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Background } from './Background';
import { Character, AnimationState, Direction } from './Character';
import { SelectionBubble } from './SelectionBubble';
import { useCharacterController } from './hooks/useCharacterController';
import { useGameLoop } from './hooks/useGameLoop';

// Fun facts - first one is always shown first, rest are randomized
const FIRST_FACT = "My name is Kyll, pronounced Kyle.";
const OTHER_FACTS = [
  "I have a beautiful dog named Moze.",
  "Our little one is 1 year old.",
  "I grew up in the outback of South Australia.",
  "I built an AFL app to help me better identify fun facts.",
  "I have 5 siblings — 3 sisters and 2 brothers.",
  "My favourite drink is coffee.",
  "My favourite food is schnitzel.",
  "My favourite pastimes include board games, golf, and building fun apps like this.",
];

// Special messages
const FOURTH_CLICK_MESSAGE = "I love that you're getting to know me better! How about you give me a call and I can learn about you?";
const ALL_FACTS_MESSAGE = "That's all I have to share about myself. If you'd like to learn more, consider flicking me a call!";

// Constants
const MOVEMENT_SPEED = 0.03; // percentage per ms
const LEFT_TARGET_X = 20; // Resume position
const RIGHT_TARGET_X = 80; // AFL App position
const TARGET_THRESHOLD = 2; // How close to be "at" the target
const JUMP_DURATION = 600; // ms

// State types
type TargetSelection = 'resume' | 'afl' | null;

interface GameState {
  characterX: number;
  direction: Direction;
  animationState: AnimationState;
  targetSelection: TargetSelection;
  isAutoWalking: boolean;
  isJumping: boolean;
}

// Actions
type GameAction =
  | { type: 'MOVE_LEFT' }
  | { type: 'MOVE_RIGHT' }
  | { type: 'STOP_MOVING' }
  | { type: 'UPDATE_POSITION'; deltaTime: number }
  | { type: 'SELECT_TARGET'; target: TargetSelection }
  | { type: 'REACH_TARGET' }
  | { type: 'START_JUMP' }
  | { type: 'COMPLETE_JUMP' };

const initialState: GameState = {
  characterX: 50,
  direction: 'right',
  animationState: 'idle',
  targetSelection: null,
  isAutoWalking: false,
  isJumping: false,
};

function gameReducer(state: GameState, action: GameAction): GameState {
  switch (action.type) {
    case 'MOVE_LEFT':
      return {
        ...state,
        direction: 'left',
        animationState: 'walking',
      };

    case 'MOVE_RIGHT':
      return {
        ...state,
        direction: 'right',
        animationState: 'walking',
      };

    case 'STOP_MOVING':
      if (state.isAutoWalking) return state;
      return {
        ...state,
        animationState: 'idle',
      };

    case 'UPDATE_POSITION': {
      if (state.animationState !== 'walking') return state;

      const delta = action.deltaTime * MOVEMENT_SPEED;
      let newX = state.characterX;

      if (state.direction === 'left') {
        newX = Math.max(10, state.characterX - delta);
      } else {
        newX = Math.min(90, state.characterX + delta);
      }

      return {
        ...state,
        characterX: newX,
      };
    }

    case 'SELECT_TARGET': {
      if (state.isAutoWalking || state.isJumping) return state;

      const targetX = action.target === 'resume' ? LEFT_TARGET_X : RIGHT_TARGET_X;
      const newDirection: Direction = targetX < state.characterX ? 'left' : 'right';

      return {
        ...state,
        targetSelection: action.target,
        isAutoWalking: true,
        direction: newDirection,
        animationState: 'walking',
      };
    }

    case 'REACH_TARGET':
      return {
        ...state,
        animationState: 'idle',
      };

    case 'START_JUMP':
      return {
        ...state,
        isJumping: true,
        animationState: 'jumping',
      };

    case 'COMPLETE_JUMP':
      return {
        ...state,
        isJumping: false,
        isAutoWalking: false,
      };

    default:
      return state;
  }
}

export const GameScene: React.FC = () => {
  const navigate = useNavigate();
  const [state, dispatch] = useReducer(gameReducer, initialState);
  const [currentFact, setCurrentFact] = useState<string | null>(null);
  const [factClickCount, setFactClickCount] = useState(0);
  const [shownFacts, setShownFacts] = useState<Set<number>>(new Set());
  const jumpTimeoutRef = useRef<NodeJS.Timeout>();
  const factTimeoutRef = useRef<NodeJS.Timeout>();
  const navigationRef = useRef<string | null>(null);

  // Handle spacebar jump
  const handleJump = useCallback(() => {
    if (state.isJumping || state.isAutoWalking) return;

    dispatch({ type: 'START_JUMP' });

    setTimeout(() => {
      dispatch({ type: 'COMPLETE_JUMP' });
    }, JUMP_DURATION);
  }, [state.isJumping, state.isAutoWalking]);

  const { keysPressed } = useCharacterController({
    disabled: state.isAutoWalking,
    onJump: handleJump,
  });

  // Handle showing fun facts with special messages at milestones
  const handleFunFact = useCallback(() => {
    const newClickCount = factClickCount + 1;
    setFactClickCount(newClickCount);

    // Clear any existing timeout
    if (factTimeoutRef.current) {
      clearTimeout(factTimeoutRef.current);
    }

    let factToShow: string;

    // First click - always show the name pronunciation fact
    if (newClickCount === 1) {
      factToShow = FIRST_FACT;
    }
    // 4th click - show the "getting to know me" message
    else if (newClickCount === 4) {
      factToShow = FOURTH_CLICK_MESSAGE;
    }
    // 9th+ click (all 8 facts shown + the 4th click message) - show completion message
    else if (newClickCount > OTHER_FACTS.length + 2) {
      factToShow = ALL_FACTS_MESSAGE;
    }
    // Otherwise, show a random unshown fact
    else {
      const availableFacts = OTHER_FACTS
        .map((fact, index) => ({ fact, index }))
        .filter(({ index }) => !shownFacts.has(index));

      if (availableFacts.length > 0) {
        const randomIndex = Math.floor(Math.random() * availableFacts.length);
        const selected = availableFacts[randomIndex];
        factToShow = selected.fact;
        setShownFacts(prev => new Set(prev).add(selected.index));
      } else {
        // All facts shown, show completion message
        factToShow = ALL_FACTS_MESSAGE;
      }
    }

    setCurrentFact(factToShow);

    // Hide the fact after 5 seconds (longer for messages)
    const timeout = factToShow === FOURTH_CLICK_MESSAGE || factToShow === ALL_FACTS_MESSAGE ? 6000 : 4000;
    factTimeoutRef.current = setTimeout(() => {
      setCurrentFact(null);
    }, timeout);
  }, [factClickCount, shownFacts]);

  // Handle keyboard input
  useEffect(() => {
    if (state.isAutoWalking) return;

    const hasLeft = keysPressed.has('ArrowLeft');
    const hasRight = keysPressed.has('ArrowRight');

    if (hasLeft && !hasRight) {
      dispatch({ type: 'MOVE_LEFT' });
    } else if (hasRight && !hasLeft) {
      dispatch({ type: 'MOVE_RIGHT' });
    } else if (!hasLeft && !hasRight) {
      dispatch({ type: 'STOP_MOVING' });
    }
  }, [keysPressed, state.isAutoWalking]);

  // Game loop tick handler
  const handleTick = useCallback(
    (deltaTime: number) => {
      dispatch({ type: 'UPDATE_POSITION', deltaTime });

      // Check if we've reached the target during auto-walk
      if (state.isAutoWalking && state.targetSelection) {
        const targetX = state.targetSelection === 'resume' ? LEFT_TARGET_X : RIGHT_TARGET_X;
        const distance = Math.abs(state.characterX - targetX);

        if (distance < TARGET_THRESHOLD) {
          dispatch({ type: 'REACH_TARGET' });
          dispatch({ type: 'START_JUMP' });

          // Store the navigation target
          navigationRef.current = state.targetSelection === 'resume' ? '/resume' : '/afl';

          // Navigate after jump completes
          jumpTimeoutRef.current = setTimeout(() => {
            dispatch({ type: 'COMPLETE_JUMP' });
            if (navigationRef.current) {
              navigate(navigationRef.current);
            }
          }, JUMP_DURATION);
        }
      }
    },
    [state.isAutoWalking, state.targetSelection, state.characterX, navigate]
  );

  // Run game loop
  useGameLoop({
    onTick: handleTick,
    isRunning: state.animationState === 'walking' || state.isAutoWalking,
  });

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (jumpTimeoutRef.current) {
        clearTimeout(jumpTimeoutRef.current);
      }
      if (factTimeoutRef.current) {
        clearTimeout(factTimeoutRef.current);
      }
    };
  }, []);

  const handleSelectResume = useCallback(() => {
    dispatch({ type: 'SELECT_TARGET', target: 'resume' });
  }, []);

  const handleSelectAFL = useCallback(() => {
    dispatch({ type: 'SELECT_TARGET', target: 'afl' });
  }, []);

  return (
    <div className="relative w-full h-screen overflow-hidden bg-sky-100">
      {/* Background */}
      <Background />

      {/* Selection bubbles */}
      <SelectionBubble
        label="Resume"
        position="left"
        onClick={handleSelectResume}
        isActive={state.targetSelection === 'resume'}
        icon="resume"
      />
      <SelectionBubble
        label="AFL AI Agent"
        position="right"
        onClick={handleSelectAFL}
        isActive={state.targetSelection === 'afl'}
        icon="afl"
      />

      {/* Fun fact button - center */}
      <button
        onClick={handleFunFact}
        className="absolute top-28 left-1/2 -translate-x-1/2 px-6 py-3 rounded-full bg-yellow-400 hover:bg-yellow-300 text-gray-800 font-semibold shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-105 focus:outline-none focus:ring-4 focus:ring-yellow-300"
      >
        ✨ Fun fact about me!
      </button>

      {/* Character container - positioned at bottom */}
      <div className="absolute bottom-0 left-0 right-0 h-[70%]">
        <Character
          x={state.characterX}
          direction={state.direction}
          animationState={state.animationState}
          speechBubble={currentFact}
        />
      </div>

      {/* Instructions */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 text-center">
        <p className="text-gray-600 text-sm bg-white/70 px-4 py-2 rounded-full backdrop-blur-sm">
          Use <kbd className="px-2 py-1 bg-gray-200 rounded text-xs font-mono">←</kbd>{' '}
          <kbd className="px-2 py-1 bg-gray-200 rounded text-xs font-mono">→</kbd> to walk,{' '}
          <kbd className="px-2 py-1 bg-gray-200 rounded text-xs font-mono">space</kbd> to jump,
          or click a destination
        </p>
      </div>

      {/* Title */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 text-center">
        <h1 className="text-3xl font-bold text-gray-800 drop-shadow-sm">Kyll Hutchens</h1>
        <p className="text-gray-600">Welcome to my portfolio!</p>
      </div>
    </div>
  );
};
