import React, { useState, useRef } from 'react';
import { Note, Voice } from '../types';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type ScoreGridProps = {
  notes: Note[];
  onGridClick: (pitch: number, step: number) => void;
  onDrawEnd?: (path: {step: number, pitch: number}[]) => void;
  totalSteps: number;
  totalPitches: number;
  activeStep?: number | null;
  mode?: 'idle' | 'countin' | 'recording' | 'playing';
};

const CELL_WIDTH = 48;
const CELL_HEIGHT = 16;
const NOTE_HEAD_WIDTH = 24;
const NOTE_HEAD_HEIGHT = 16;
const NOTE_CONTAINER_WIDTH = 34;
const NOTE_CONTAINER_HEIGHT = 26;

const STAFF_LINES = [4, 6, 8, 10, 12];

const COLORS: Record<Voice, string> = {
  user: '#2D1B15',
  alto: '#C2410C',
  tenor: '#988A75',
  bass: '#31304D',
};

const ScoreGrid: React.FC<ScoreGridProps> = ({
  notes,
  onGridClick,
  onDrawEnd,
  totalSteps,
  totalPitches,
  activeStep = null,
  mode = 'idle',
}) => {
  const [hoverPos, setHoverPos] = useState<{ step: number; pitch: number } | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawPath, setDrawPath] = useState<{step: number, pitch: number}[]>([]);
  const drawPathRef = useRef<{step: number, pitch: number}[]>([]);

  const getColor = (voice: Voice) => COLORS[voice];

  const ledgerLines = notes.flatMap((note) => {
    // Render a ledger line (加线) that matches note color
    const color = getColor(note.voice);
    const lines: Array<{ key: string; left: number; top: number; color: string }> = [];
    const roundedPitch = Math.round(note.pitch);

    // Above the staff
    if (roundedPitch < STAFF_LINES[0]) {
      for (let i = STAFF_LINES[0] - 2; i >= roundedPitch; i -= 2) {
        lines.push({
          key: `ledger-above-${note.id}-${i}`,
          left: note.step * CELL_WIDTH + CELL_WIDTH / 2,
          top: i * CELL_HEIGHT + CELL_HEIGHT / 2 - 1,
          color,
        });
      }
    }
    // Below the staff
    if (roundedPitch > STAFF_LINES[STAFF_LINES.length - 1]) {
      for (let i = STAFF_LINES[STAFF_LINES.length - 1] + 2; i <= roundedPitch; i += 2) {
        lines.push({
          key: `ledger-below-${note.id}-${i}`,
          left: note.step * CELL_WIDTH + CELL_WIDTH / 2,
          top: i * CELL_HEIGHT + CELL_HEIGHT / 2 - 1,
          color,
        });
      }
    }
    return lines;
  });

  return (
    <div className="relative p-6 bg-white/50 backdrop-blur-md rounded-3xl border border-[#EFEBE1] shadow-xl overflow-hidden">
      <div className="absolute top-0 left-0 w-8 h-8 border-t-2 border-l-2 border-[#D7CCC8] rounded-tl-3xl m-3" />
      <div className="absolute top-0 right-0 w-8 h-8 border-t-2 border-r-2 border-[#D7CCC8] rounded-tr-3xl m-3" />
      <div className="absolute bottom-0 left-0 w-8 h-8 border-b-2 border-l-2 border-[#D7CCC8] rounded-bl-3xl m-3" />
      <div className="absolute bottom-0 right-0 w-8 h-8 border-b-2 border-r-2 border-[#D7CCC8] rounded-br-3xl m-3" />

      <div 
        className="relative select-none touch-none bg-[#FDFBF7] rounded-xl pl-16 pr-4 pt-4 pb-4"
      >
        <div className="relative" style={{ width: totalSteps * CELL_WIDTH, height: totalPitches * CELL_HEIGHT }}>
        {ledgerLines.map((l) => (
          <div
            key={l.key}
            className="absolute pointer-events-none z-10"
            style={{
              left: l.left - CELL_WIDTH * 0.45,
              top: l.top,
              width: CELL_WIDTH * 0.9,
              height: 2,
              backgroundColor: l.color,
            }}
          />
        ))}

        {STAFF_LINES.map((pitch) => (
          <div
            key={`staff-line-${pitch}`}
            className="absolute left-0 w-full border-t-[2px] border-[#2D1B15] pointer-events-none"
            style={{ top: pitch * CELL_HEIGHT + CELL_HEIGHT / 2 - 1 }}
          />
        ))}

        {Array.from({ length: totalSteps / 4 + 1 }).map((_, i) => (
          <div
            key={`bar-${i}`}
            className="absolute border-l-[2px] border-[#2D1B15] pointer-events-none z-10"
            style={{ 
              left: i * 4 * CELL_WIDTH,
              top: STAFF_LINES[0] * CELL_HEIGHT + CELL_HEIGHT / 2 - 1,
              height: (STAFF_LINES[STAFF_LINES.length - 1] - STAFF_LINES[0]) * CELL_HEIGHT + 2
            }}
          />
        ))}

        {Array.from({ length: totalSteps + 1 }).map((_, i) => {
          if (i % 4 === 0) return null;
          return (
            <div
              key={`v-${i}`}
              className="absolute top-0 h-full pointer-events-none border-l border-[#D7CCC8]/40"
              style={{ left: i * CELL_WIDTH }}
            />
          );
        })}

        <div className="absolute left-[-6px] top-0 bottom-0 flex items-center justify-center pointer-events-none z-10">
          <span
            className="select-none"
            style={{
              fontSize: 128,
              lineHeight: '1',
              color: '#2D1B15',
              transform: 'translateY(-14px)',
              fontFamily: '"Noto Music","Playfair Display",serif',
              opacity: 0.9,
            }}
          >
            𝄞
          </span>
        </div>

        {activeStep !== null && (mode === 'playing' || mode === 'recording') && (
          <div
            className="absolute top-0 bottom-0 pointer-events-none z-10"
            style={{
              left: activeStep * CELL_WIDTH,
              width: 2,
              backgroundColor: mode === 'playing' ? '#2D1B15' : '#C2410C',
              opacity: 0.35,
            }}
          />
        )}

        <div 
          className="absolute inset-0 z-10 cursor-crosshair touch-none"
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            const rect = e.currentTarget.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const step = x / CELL_WIDTH;
            const pitch = y / CELL_HEIGHT;
            
            setIsDrawing(true);
            const initialPath = [{step, pitch}];
            drawPathRef.current = initialPath;
            setDrawPath(initialPath);
          }}
          onPointerMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const step = x / CELL_WIDTH;
            const pitch = y / CELL_HEIGHT;
            
            if (isDrawing) {
              const newPath = [...drawPathRef.current, {step, pitch}];
              drawPathRef.current = newPath;
              setDrawPath(newPath);
            } else {
              if (step >= 0 && step < totalSteps && pitch >= 0 && pitch < totalPitches) {
                setHoverPos({ step, pitch });
              } else {
                setHoverPos(null);
              }
            }
          }}
          onPointerUp={(e) => {
            e.currentTarget.releasePointerCapture(e.pointerId);
            if (isDrawing) {
              setIsDrawing(false);
              const path = drawPathRef.current;
              if (path.length > 0) {
                const start = path[0];
                const end = path[path.length - 1];
                const dist = Math.hypot((end.step - start.step) * CELL_WIDTH, (end.pitch - start.pitch) * CELL_HEIGHT);
                
                if (dist < 10) {
                  onGridClick(start.pitch, start.step);
                } else if (onDrawEnd) {
                  onDrawEnd(path);
                }
              }
              drawPathRef.current = [];
              setDrawPath([]);
            }
          }}
          onPointerCancel={(e) => {
            e.currentTarget.releasePointerCapture(e.pointerId);
            setIsDrawing(false);
            drawPathRef.current = [];
            setDrawPath([]);
          }}
          onPointerLeave={() => {
            if (!isDrawing) setHoverPos(null);
          }}
        />

        {drawPath.length > 0 && (
          <svg className="absolute inset-0 pointer-events-none z-30" style={{ width: totalSteps * CELL_WIDTH, height: totalPitches * CELL_HEIGHT }}>
            <polyline
              points={drawPath.map(p => `${p.step * CELL_WIDTH},${p.pitch * CELL_HEIGHT}`).join(' ')}
              fill="none"
              stroke={COLORS.user}
              strokeWidth="4"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity="0.6"
            />
          </svg>
        )}

        {hoverPos && (
          <div
            className="absolute pointer-events-none z-10"
            style={{
              left: hoverPos.step * CELL_WIDTH + (CELL_WIDTH - NOTE_CONTAINER_WIDTH) / 2,
              top: hoverPos.pitch * CELL_HEIGHT + CELL_HEIGHT / 2 - NOTE_CONTAINER_HEIGHT / 2,
              width: NOTE_CONTAINER_WIDTH,
              height: NOTE_CONTAINER_HEIGHT,
            }}
          >
            {/* Hover preview ledger lines */}
            {Math.round(hoverPos.pitch) < STAFF_LINES[0] && Array.from({ length: Math.floor((STAFF_LINES[0] - Math.round(hoverPos.pitch)) / 2) }).map((_, i) => (
              <div
                key={`hover-ledger-above-${i}`}
                className="absolute"
                style={{
                  left: NOTE_CONTAINER_WIDTH / 2 - CELL_WIDTH * 0.45,
                  top: NOTE_CONTAINER_HEIGHT / 2 + (STAFF_LINES[0] - hoverPos.pitch - (i + 1) * 2) * CELL_HEIGHT - 1,
                  width: CELL_WIDTH * 0.9,
                  height: 2,
                  backgroundColor: COLORS.user,
                  opacity: 0.3,
                }}
              />
            ))}
            {Math.round(hoverPos.pitch) > STAFF_LINES[STAFF_LINES.length - 1] && Array.from({ length: Math.floor((Math.round(hoverPos.pitch) - STAFF_LINES[STAFF_LINES.length - 1]) / 2) }).map((_, i) => (
              <div
                key={`hover-ledger-below-${i}`}
                className="absolute"
                style={{
                  left: NOTE_CONTAINER_WIDTH / 2 - CELL_WIDTH * 0.45,
                  top: NOTE_CONTAINER_HEIGHT / 2 - (hoverPos.pitch - STAFF_LINES[STAFF_LINES.length - 1] - (i + 1) * 2) * CELL_HEIGHT - 1,
                  width: CELL_WIDTH * 0.9,
                  height: 2,
                  backgroundColor: COLORS.user,
                  opacity: 0.3,
                }}
              />
            ))}

            {(Math.round(hoverPos.pitch) === 4 || Math.round(hoverPos.pitch) === 11) && (
              <span className="absolute text-[#2D1B15] font-bold" style={{ left: -14, top: '50%', transform: 'translateY(-50%)', fontSize: 20, fontFamily: 'serif', opacity: 0.3 }}>♯</span>
            )}
            <div
              className="absolute left-1/2 top-1/2 rounded-full opacity-30"
              style={{
                width: NOTE_HEAD_WIDTH,
                height: NOTE_HEAD_HEIGHT,
                backgroundColor: COLORS.user,
                transform: 'translate(-50%, -50%) rotate(-18deg)',
              }}
            />
          </div>
        )}

        <AnimatePresence>
          {notes.map((note) => (
            <motion.div
              key={note.id}
              initial={{
                scale: 0.7,
                opacity: 0,
                y: -7,
                left: note.step * CELL_WIDTH + (CELL_WIDTH - NOTE_CONTAINER_WIDTH) / 2,
                top: note.pitch * CELL_HEIGHT + CELL_HEIGHT / 2 - NOTE_CONTAINER_HEIGHT / 2,
              }}
              animate={{ 
                scale:
                  mode === 'playing' && activeStep !== null && Math.round(note.step) === activeStep
                    ? [1, 1.13, 1]
                    : 1,
                opacity: 1, 
                y: 0,
                left: note.step * CELL_WIDTH + (CELL_WIDTH - NOTE_CONTAINER_WIDTH) / 2,
                top: note.pitch * CELL_HEIGHT + CELL_HEIGHT / 2 - NOTE_CONTAINER_HEIGHT / 2,
              }}
              exit={{ scale: 0, opacity: 0, transition: { duration: 0.15 } }}
              transition={{ 
                type: "spring", 
                stiffness: 400, 
                damping: 25,
                delay: note.voice === 'user' ? 0 : note.step * 0.05 + (Math.random() * 0.1),
              }}
              className="absolute pointer-events-none z-20"
              style={{
                width: NOTE_CONTAINER_WIDTH,
                height: NOTE_CONTAINER_HEIGHT,
              }}
            >
              {(Math.round(note.pitch) === 4 || Math.round(note.pitch) === 11) && (
                <span className="absolute font-bold" style={{ color: getColor(note.voice), left: -14, top: '50%', transform: 'translateY(-50%)', fontSize: 20, fontFamily: 'serif' }}>♯</span>
              )}
              <div
                className={cn("absolute left-1/2 top-1/2 rounded-full shadow-sm", note.voice === 'user' ? "opacity-95" : "opacity-90")}
                style={{
                  width: NOTE_HEAD_WIDTH,
                  height: NOTE_HEAD_HEIGHT,
                  backgroundColor: getColor(note.voice),
                  transform: 'translate(-50%, -50%) rotate(-18deg)',
                }}
              />
            </motion.div>
          ))}
        </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

export default ScoreGrid;
