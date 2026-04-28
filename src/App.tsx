import { useState, useCallback, useRef, useEffect } from 'react';
import ScoreGrid from './components/ScoreGrid';
import ControlBar from './components/ControlBar';
import TransportBar, { type TransportMode } from './components/TransportBar';
import { Note, Voice } from './types';

const generateId = () => Math.random().toString(36).substring(2, 9);

const TOTAL_STEPS = 16;
const TOTAL_PITCHES = 15;
const PLAY_BPM = 200;
const RECORD_BPM = 100;
const RECORD_OCTAVE_SHIFT = 12;
const AI_API_URL = 'http://43.129.229.99:8000/generate';
const AI_REQUEST_TIMEOUT_MS = 15000;

const PITCH_TO_MIDI: Record<number, number> = {
  14: 60, // C4
  13: 62, // D4
  12: 64, // E4
  11: 66, // F#4
  10: 67, // G4
  9: 69,  // A4
  8: 71,  // B4
  7: 72,  // C5
  6: 74,  // D5
  5: 76,  // E5
  4: 78,  // F#5
  3: 79,  // G5
  2: 81,  // A5
  1: 83,  // B5
  0: 84   // C6
};

const VOICE_SYNTHS: Record<Voice, {
  type: OscillatorType;
  gain: number;
  attack: number;
  release: number;
  transpose: number;
  pan: number;
}> = {
  user: {
    type: 'triangle',
    gain: 0.22,
    attack: 0.02,
    release: 0.08,
    transpose: -12,
    pan: -0.15,
  },
  alto: {
    type: 'sine',
    gain: 0.16,
    attack: 0.03,
    release: 0.1,
    transpose: 0,
    pan: -0.35,
  },
  tenor: {
    type: 'square',
    gain: 0.12,
    attack: 0.015,
    release: 0.08,
    transpose: -12,
    pan: 0.2,
  },
  bass: {
    type: 'sawtooth',
    gain: 0.08,
    attack: 0.01,
    release: 0.12,
    transpose: -24,
    pan: 0.4,
  },
};

// 定义敦煌/雅乐音阶对应的相对音阶度数（0=Do, 1=Re, 2=Mi, 3=Fa#, 4=Sol, 5=La）
// 在 C 大调下，相当于 C, D, E, F#, G, A
// 五线谱上，我们的 pitch 是从上往下数的线和间。
// 为了简单起见，我们假设五线谱上的 15 个格子循环这 6 个音。
// 正常的 C 大调（没有升降号的白键）是 1 2 3 4 5 6 7
// 我们需要吸附到 1 2 3 #4 5 6 上（去掉 7，把 4 变成 #4）
// 这里我们定义一个“允许的 pitch 集合”。
// 假设 pitch 0 是高音的某一个音，我们通过简单的映射来决定。
// 假设标准的五线谱线间关系对应 C 大调的白键，那么 7 个音符是一个循环。
// 我们的敦煌音阶是 1, 2, 3, 4(实际代表#4), 5, 6
// 被剔除的音是 7（即 C 大调的 B）。
// 我们可以根据 pitch 的 index 对 7 取模，来判断它对应哪个音符。
// 假设 pitch 14 (最下面的线/下加一线下方) 是 C (1)
// 14: 1 (C)
// 13: 2 (D)
// 12: 3 (E)
// 11: 4 (F / F#)
// 10: 5 (G)
// 9: 6 (A)
// 8: 7 (B) -> 不允许
// 7: 1 (C)
// 6: 2 (D)
// 5: 3 (E)
// 4: 4 (F / F#)
// 3: 5 (G)
// 2: 6 (A)
// 1: 7 (B) -> 不允许
// 0: 1 (C)
const ALLOWED_PITCHES = [0, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14];

export const snapToDunhuangPitch = (rawPitch: number) => {
  const pitch = Math.round(rawPitch);
  if (ALLOWED_PITCHES.includes(pitch)) return pitch;
  
  // 找最近的
  let closest = ALLOWED_PITCHES[0];
  let minDiff = Math.abs(pitch - closest);
  for (const p of ALLOWED_PITCHES) {
    const diff = Math.abs(pitch - p);
    if (diff < minDiff) {
      minDiff = diff;
      closest = p;
    }
  }
  return closest;
};

const median = (values: number[]) => {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) return (sorted[mid - 1] + sorted[mid]) / 2;
  return sorted[mid];
};

const freqToMidi = (freq: number) => 69 + 12 * Math.log2(freq / 440);

const midiToPitchIndex = (midi: number, midiOffset: number = 0) => {
  let bestPitchIndex = 0;
  let bestDiff = Infinity;
  for (const [pitchIndexStr, baseMidi] of Object.entries(PITCH_TO_MIDI)) {
    const pitchIndex = Number(pitchIndexStr);
    const diff = Math.abs(midi - (baseMidi + midiOffset));
    if (diff < bestDiff) {
      bestDiff = diff;
      bestPitchIndex = pitchIndex;
    }
  }
  return bestPitchIndex;
};

const midiToNoteName = (midi: number) => {
  const names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  const n = Math.round(midi);
  const name = names[((n % 12) + 12) % 12];
  const octave = Math.floor(n / 12) - 1;
  return `${name}${octave}`;
};

const pitchIndexToNoteName = (pitchIndex: number) => {
  const midi = PITCH_TO_MIDI[Math.round(pitchIndex)];
  if (midi === undefined) return '';
  return midiToNoteName(midi);
};

const autoCorrelate = (buf: Float32Array, sampleRate: number) => {
  const SIZE = buf.length;
  let rms = 0;
  for (let i = 0; i < SIZE; i++) rms += buf[i] * buf[i];
  rms = Math.sqrt(rms / SIZE);
  if (rms < 0.01) return null;

  let r1 = 0;
  let r2 = SIZE - 1;
  const threshold = 0.2;
  for (let i = 0; i < SIZE / 2; i++) {
    if (Math.abs(buf[i]) < threshold) {
      r1 = i;
      break;
    }
  }
  for (let i = 1; i < SIZE / 2; i++) {
    if (Math.abs(buf[SIZE - i]) < threshold) {
      r2 = SIZE - i;
      break;
    }
  }

  const trimmed = buf.slice(r1, r2);
  const trimmedSize = trimmed.length;
  const c = new Array(trimmedSize).fill(0);
  for (let i = 0; i < trimmedSize; i++) {
    for (let j = 0; j < trimmedSize - i; j++) {
      c[i] = c[i] + trimmed[j] * trimmed[j + i];
    }
  }

  let d = 0;
  while (c[d] > c[d + 1]) d++;

  let maxValue = -1;
  let maxIndex = -1;
  for (let i = d; i < trimmedSize; i++) {
    if (c[i] > maxValue) {
      maxValue = c[i];
      maxIndex = i;
    }
  }
  if (maxIndex <= 0) return null;

  const x1 = c[maxIndex - 1];
  const x2 = c[maxIndex];
  const x3 = c[maxIndex + 1];
  const a = (x1 + x3 - 2 * x2) / 2;
  const b = (x3 - x1) / 2;
  const shift = a ? b / (2 * a) : 0;
  const period = maxIndex + shift;

  if (!isFinite(period) || period <= 0) return null;
  return sampleRate / period;
};

const getSnappedNotes = (currentNotes: Note[]): Note[] => {
  const userNotes = currentNotes.filter(n => n.voice === 'user');
  const otherNotes = currentNotes.filter(n => n.voice !== 'user');

  const snappedUserNotes: Note[] = [];
  const usedSteps = new Set<number>();

  const sortedUserNotes = [...userNotes].sort((a, b) => a.step - b.step);

  sortedUserNotes.forEach(n => {
    let snappedStep = Math.round(n.step);
    snappedStep = Math.max(0, Math.min(TOTAL_STEPS - 1, snappedStep));
    
    const snappedPitch = snapToDunhuangPitch(Math.round(n.pitch));

    if (!usedSteps.has(snappedStep)) {
      usedSteps.add(snappedStep);
      snappedUserNotes.push({
        ...n,
        step: snappedStep,
        pitch: snappedPitch
      });
    }
  });

  return [...otherNotes, ...snappedUserNotes];
};

const scheduleNotePlayback = (
  ctx: AudioContext,
  note: Note,
  noteStartTime: number,
  stepDuration: number
) => {
  const midi = PITCH_TO_MIDI[Math.round(note.pitch)];
  if (midi === undefined) return;

  const synth = VOICE_SYNTHS[note.voice];
  const transposedMidi = midi + synth.transpose;
  const freq = 440 * Math.pow(2, (transposedMidi - 69) / 12);
  const noteEndTime = noteStartTime + stepDuration;

  const osc = ctx.createOscillator();
  const gainNode = ctx.createGain();
  const outputNode =
    typeof ctx.createStereoPanner === 'function' ? ctx.createStereoPanner() : null;

  osc.type = synth.type;
  osc.frequency.setValueAtTime(freq, noteStartTime);

  gainNode.gain.setValueAtTime(0, noteStartTime);
  gainNode.gain.linearRampToValueAtTime(synth.gain, noteStartTime + synth.attack);
  gainNode.gain.setValueAtTime(
    synth.gain,
    Math.max(noteStartTime + synth.attack, noteEndTime - synth.release)
  );
  gainNode.gain.linearRampToValueAtTime(0, noteEndTime);

  osc.connect(gainNode);
  if (outputNode) {
    outputNode.pan.setValueAtTime(synth.pan, noteStartTime);
    gainNode.connect(outputNode);
    outputNode.connect(ctx.destination);
  } else {
    gainNode.connect(ctx.destination);
  }

  osc.start(noteStartTime);
  osc.stop(noteEndTime);
};

const formatAiErrorMessage = (error: unknown) => {
  if (error instanceof DOMException && error.name === 'AbortError') {
    return 'AI 服务器响应超时（15 秒）。可能是后端正在重启，或当前推理耗时过长。';
  }

  if (error instanceof Error) {
    const message = error.message.trim();
    if (message !== '') {
      return `AI 生成失败：${message}`;
    }
  }

  return 'AI 服务器连接失败。可能原因包括后端未启动、网络不可达，或浏览器当前无法访问 AI 接口。';
};

const formatRecordErrorMessage = (error: unknown) => {
  if (!window.isSecureContext) {
    return '当前页面不是安全上下文，浏览器会禁用麦克风。录音功能需要 HTTPS，或在 localhost 下访问。';
  }

  if (error instanceof DOMException) {
    switch (error.name) {
      case 'NotAllowedError':
      case 'PermissionDeniedError':
        return '浏览器没有拿到麦克风权限。请在地址栏或系统设置里允许当前页面访问麦克风。';
      case 'NotFoundError':
      case 'DevicesNotFoundError':
        return '没有检测到可用的麦克风设备。请确认麦克风已连接并可被系统识别。';
      case 'NotReadableError':
      case 'TrackStartError':
        return '麦克风当前被其他应用占用，或系统暂时无法读取音频输入。';
      case 'SecurityError':
        return '浏览器安全策略阻止了录音。通常需要 HTTPS 环境和麦克风权限。';
      default:
        return `录音启动失败：${error.message || error.name}`;
    }
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    return '当前浏览器环境不支持麦克风录音，或页面不是 HTTPS / localhost。';
  }

  return '录音启动失败。请检查麦克风权限、浏览器安全设置，以及是否通过 HTTPS 访问页面。';
};

function App() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isCountingIn, setIsCountingIn] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [transportMode, setTransportMode] = useState<TransportMode>('idle');
  const [activeStep, setActiveStep] = useState<number | null>(null);
  const [countInBeat, setCountInBeat] = useState<number | null>(null);
  const [detectText, setDetectText] = useState<string>('');
  
  const audioCtxRef = useRef<AudioContext | null>(null);
  const playTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const playRafRef = useRef<number | null>(null);
  const playStartRef = useRef<number>(0);
  const playStepDurationRef = useRef<number>(0);
  const recordCtxRef = useRef<AudioContext | null>(null);
  const recordIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recordTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countInTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const recordRafRef = useRef<number | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const isRecordingRef = useRef(false);
  const recordBucketsRef = useRef<number[][]>([]);
  const recordStartTimeRef = useRef<number>(0);
  const recordStepDurationRef = useRef<number>(0);
  const userNoteIdsByStepRef = useRef<Record<number, string>>({});
  const lastCommittedStepRef = useRef<number>(-1);

  const stopPlayback = useCallback(() => {
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }
    if (playTimeoutRef.current) {
      clearTimeout(playTimeoutRef.current);
      playTimeoutRef.current = null;
    }
    if (playRafRef.current !== null) {
      cancelAnimationFrame(playRafRef.current);
      playRafRef.current = null;
    }
    setIsPlaying(false);
    setTransportMode('idle');
    setActiveStep(null);
  }, []);

  const stopRecording = useCallback(() => {
    if (countInTimeoutRef.current) {
      clearTimeout(countInTimeoutRef.current);
      countInTimeoutRef.current = null;
    }
    if (recordTimeoutRef.current) {
      clearTimeout(recordTimeoutRef.current);
      recordTimeoutRef.current = null;
    }
    if (recordIntervalRef.current) {
      clearInterval(recordIntervalRef.current);
      recordIntervalRef.current = null;
    }
    if (recordRafRef.current !== null) {
      cancelAnimationFrame(recordRafRef.current);
      recordRafRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    analyserRef.current = null;
    isRecordingRef.current = false;
    if (recordCtxRef.current) {
      recordCtxRef.current.close();
      recordCtxRef.current = null;
    }
    setIsCountingIn(false);
    setIsRecording(false);
    setTransportMode('idle');
    setActiveStep(null);
    setCountInBeat(null);
    setDetectText('');
    lastCommittedStepRef.current = -1;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopPlayback();
      stopRecording();
    };
  }, [stopPlayback, stopRecording]);

  const handlePlay = useCallback(() => {
    if (isCountingIn || isRecording) return;
    if (isPlaying) {
      stopPlayback();
      return;
    }

    // 更新状态，触发 React 渲染动画
    const snappedNotes = getSnappedNotes(notes);
    setNotes(snappedNotes);

    setIsPlaying(true);
    setTransportMode('playing');

    setTimeout(() => {
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioContextClass) {
        setIsPlaying(false);
        setTransportMode('idle');
        return;
      }
      const ctx = new AudioContextClass();
      audioCtxRef.current = ctx;
      void ctx.resume();

      const stepDuration = 60 / PLAY_BPM;
      const startTime = ctx.currentTime + 0.1;
      playStartRef.current = startTime;
      playStepDurationRef.current = stepDuration;

      snappedNotes.forEach((note) => {
        const noteStartTime = startTime + Math.round(note.step) * stepDuration;
        scheduleNotePlayback(ctx, note, noteStartTime, stepDuration);
      });

      const totalDuration = TOTAL_STEPS * stepDuration;
      playTimeoutRef.current = setTimeout(() => {
        stopPlayback();
      }, (totalDuration + 0.5) * 1000);

      const tick = () => {
        if (!audioCtxRef.current) return;
        const t = audioCtxRef.current.currentTime - playStartRef.current;
        const step = Math.floor(t / playStepDurationRef.current);
        if (step >= 0 && step < TOTAL_STEPS) setActiveStep(step);
        playRafRef.current = requestAnimationFrame(tick);
      };
      tick();
    }, 300); // 300ms delay for animation
  }, [isCountingIn, isPlaying, isRecording, notes, stopPlayback]);

  const handleRecord = useCallback(async () => {
    if (isCountingIn || isRecording) {
      stopRecording();
      return;
    }
    if (isPlaying) stopPlayback();

    if (!navigator.mediaDevices?.getUserMedia) {
      alert('当前浏览器环境不支持麦克风录音，或页面不是 HTTPS / localhost。');
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      alert(formatRecordErrorMessage(error));
      return;
    }

    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextClass) return;

    const ctx: AudioContext = new AudioContextClass();
    await ctx.resume();
    recordCtxRef.current = ctx;
    mediaStreamRef.current = stream;

    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.2;
    source.connect(analyser);
    analyserRef.current = analyser;

    const stepDuration = 60 / RECORD_BPM;
    recordStepDurationRef.current = stepDuration;
    const baseTime = ctx.currentTime + 0.25;
    const recordStartTime = baseTime + 4 * stepDuration;
    recordStartTimeRef.current = recordStartTime;

    const clickFreq = 1000;
    for (let i = 0; i < 4; i++) {
      const t = baseTime + i * stepDuration;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = clickFreq;
      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(0.9, t + 0.002);
      gain.gain.linearRampToValueAtTime(0, t + 0.06);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(t);
      osc.stop(t + 0.08);
    }

    setNotes([]);
    setIsCountingIn(true);
    setTransportMode('countin');
    setCountInBeat(1);
    isRecordingRef.current = false;
    recordBucketsRef.current = Array.from({ length: TOTAL_STEPS }, () => []);
    userNoteIdsByStepRef.current = {};
    lastCommittedStepRef.current = -1;

    const countInTick = () => {
      if (!recordCtxRef.current) return;
      const dt = recordCtxRef.current.currentTime - baseTime;
      const beat = Math.floor(dt / stepDuration) + 1;
      const clampedBeat = Math.max(1, Math.min(4, beat));
      setCountInBeat(clampedBeat);
      if (recordCtxRef.current.currentTime >= recordStartTime) return;
      recordRafRef.current = requestAnimationFrame(countInTick);
    };
    countInTick();

    countInTimeoutRef.current = setTimeout(() => {
      setIsCountingIn(false);
      setIsRecording(true);
      setTransportMode('recording');
      setCountInBeat(null);
      setDetectText('');
      isRecordingRef.current = true;

      const buffer = new Float32Array(analyser.fftSize);
      recordIntervalRef.current = setInterval(() => {
        if (!isRecordingRef.current) return;
        const now = ctx.currentTime;
        const step = Math.floor((now - recordStartTimeRef.current) / stepDuration);
        if (step < 0 || step >= TOTAL_STEPS) return;

        analyser.getFloatTimeDomainData(buffer);
        const freq = autoCorrelate(buffer, ctx.sampleRate);
        if (freq && freq >= 80 && freq <= 1000) {
          const midi = freqToMidi(freq);
          if (isFinite(midi)) recordBucketsRef.current[step].push(midi);
        }

        if (step !== lastCommittedStepRef.current) {
          lastCommittedStepRef.current = step;
          setActiveStep(step);
        }

        const m = median(recordBucketsRef.current[step]);
        if (m !== null) {
          const minMidi = Math.min(...Object.values(PITCH_TO_MIDI));
          const maxMidi = Math.max(...Object.values(PITCH_TO_MIDI));
          let shiftedMidi = m + RECORD_OCTAVE_SHIFT;
          while (shiftedMidi < minMidi) shiftedMidi += 12;
          while (shiftedMidi > maxMidi) shiftedMidi -= 12;
          const pitchIndex = snapToDunhuangPitch(midiToPitchIndex(shiftedMidi));
          const id = userNoteIdsByStepRef.current[step] ?? generateId();
          userNoteIdsByStepRef.current[step] = id;
          setDetectText(`${midiToNoteName(m)}↑8 → ${pitchIndexToNoteName(pitchIndex)}`);
          setNotes((prev) => {
            const otherNotes = prev.filter((n) => n.voice !== 'user');
            const userNotes = prev.filter((n) => n.voice === 'user' && Math.round(n.step) !== step);
            return [...otherNotes, ...userNotes, { id, pitch: pitchIndex, step, voice: 'user' }];
          });
        }
      }, 40);

      recordTimeoutRef.current = setTimeout(() => {
        isRecordingRef.current = false;
        setIsRecording(false);
        setIsCountingIn(false);
        setTransportMode('idle');
        if (recordIntervalRef.current) {
          clearInterval(recordIntervalRef.current);
          recordIntervalRef.current = null;
        }

        const buckets = recordBucketsRef.current;
        const userNotes: Note[] = [];
        for (let step = 0; step < TOTAL_STEPS; step++) {
          const m = median(buckets[step]);
          if (m === null) continue;
          const minMidi = Math.min(...Object.values(PITCH_TO_MIDI));
          const maxMidi = Math.max(...Object.values(PITCH_TO_MIDI));
          let shiftedMidi = m + RECORD_OCTAVE_SHIFT;
          while (shiftedMidi < minMidi) shiftedMidi += 12;
          while (shiftedMidi > maxMidi) shiftedMidi -= 12;
          const pitchIndex = snapToDunhuangPitch(midiToPitchIndex(shiftedMidi));
          userNotes.push({ id: generateId(), pitch: pitchIndex, step, voice: 'user' });
        }

        setNotes(userNotes);
        setDetectText('');

        if (mediaStreamRef.current) {
          mediaStreamRef.current.getTracks().forEach((t) => t.stop());
          mediaStreamRef.current = null;
        }
        analyserRef.current = null;
        if (recordCtxRef.current) {
          recordCtxRef.current.close();
          recordCtxRef.current = null;
        }
        setActiveStep(null);
      }, TOTAL_STEPS * stepDuration * 1000 + 80);
    }, 4 * stepDuration * 1000);
  }, [isCountingIn, isRecording, isPlaying, stopPlayback, stopRecording]);

  const handleGridClick = useCallback((pitch: number, step: number) => {
    setNotes((prev) => {
      const userNotes = prev.filter((n) => n.voice === 'user');
      const otherNotes = prev.filter((n) => n.voice !== 'user');

      const clickX = step * 48; // CELL_WIDTH
      const clickY = pitch * 16; // CELL_HEIGHT
      let clickedIndex = -1;
      let minDistance = 24;

      userNotes.forEach((n, idx) => {
        const nx = n.step * 48;
        const ny = n.pitch * 16;
        const dist = Math.hypot(nx - clickX, ny - clickY);
        if (dist < minDistance) {
          minDistance = dist;
          clickedIndex = idx;
        }
      });

      if (clickedIndex >= 0) {
        userNotes.splice(clickedIndex, 1);
      } else {
        userNotes.push({ id: generateId(), pitch, step, voice: 'user' });
      }

      return [...otherNotes, ...userNotes];
    });
  }, []);

  const handleDrawEnd = useCallback((path: {step: number, pitch: number}[]) => {
    setNotes((prev) => {
      const stepPitchMap = new Map<number, number[]>();

      for (let i = 0; i < path.length - 1; i++) {
        const p1 = path[i];
        const p2 = path[i+1];
        const steps = Math.max(1, Math.abs(p2.step - p1.step) * 48);
        const numSamples = Math.ceil(steps);
        for (let j = 0; j <= numSamples; j++) {
          const t = numSamples === 0 ? 0 : j / numSamples;
          const s = p1.step + t * (p2.step - p1.step);
          const p = p1.pitch + t * (p2.pitch - p1.pitch);
          const col = Math.round(s);
          if (col >= 0 && col < TOTAL_STEPS) {
            if (!stepPitchMap.has(col)) stepPitchMap.set(col, []);
            stepPitchMap.get(col)!.push(p);
          }
        }
      }

      const newNotes: Note[] = [];
      const newCols = new Set(stepPitchMap.keys());

      for (const [col, pitches] of stepPitchMap.entries()) {
        const avgPitch = pitches.reduce((sum, p) => sum + p, 0) / pitches.length;
        newNotes.push({
          id: generateId(),
          pitch: avgPitch,
          step: col,
          voice: 'user'
        });
      }

      const otherNotes = prev.filter((n) => n.voice !== 'user');
      const userNotes = prev.filter((n) => n.voice === 'user');

      // Remove existing user notes in columns that were drawn over
      const filteredUserNotes = userNotes.filter((n) => !newCols.has(Math.round(n.step)));

      const combined = [...otherNotes, ...filteredUserNotes, ...newNotes];
      // 自动处理成符合要求的旋律
      return getSnappedNotes(combined);
    });
  }, []);

  const handleClear = useCallback(() => {
    setNotes([]);
  }, []);

  const handleHarmonize = useCallback(async () => {
    if (isCountingIn || isRecording) return;
    if (isGenerating) return;
    setIsGenerating(true);

    // 1. 先触发吸附更新
    const snappedNotes = getSnappedNotes(notes);
    setNotes(snappedNotes);

    // 2. 将用户绘制的旋律打包准备发送给 AI 服务器
    const userNotes = snappedNotes.filter((n) => n.voice === 'user');
    if (userNotes.length === 0) {
      setIsGenerating(false);
      alert('请先输入或录入主旋律，再生成和声。');
      return;
    }

    const melodyPayload = userNotes.map(n => ({
      step: n.step,
      pitch: n.pitch
    }));

    try {
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), AI_REQUEST_TIMEOUT_MS);
      try {
        // 3. 向我们刚刚搭建的腾讯云 GPU 服务器发起真实请求
        const response = await fetch(AI_API_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ melody: melodyPayload }),
          signal: controller.signal
        });

        if (!response.ok) {
          let detail = '';
          try {
            const errorData = await response.json();
            detail = typeof errorData?.detail === 'string' ? errorData.detail : JSON.stringify(errorData);
          } catch {
            detail = response.statusText;
          }
          throw new Error(`服务器返回 ${response.status}${detail ? `，${detail}` : ''}`);
        }

        const data = await response.json();
        console.log("AI 大脑返回的原始配器数据:", data);

        if (data.status === "success" && data.generated_notes) {
          // 使用 AI 服务器返回的真实音符数据
          setNotes((prev) => {
            const currentUserNotes = prev.filter((n) => n.voice === 'user');
            return [...currentUserNotes, ...data.generated_notes];
          });
        } else {
          throw new Error("API 返回格式不正确");
        }
      } finally {
        window.clearTimeout(timeoutId);
      }

    } catch (error) {
      console.error("AI 音乐生成失败:", error);
      alert(formatAiErrorMessage(error));
    } finally {
      setIsGenerating(false);
    }
  }, [isCountingIn, isGenerating, isRecording, notes]);

  return (
    <div className="min-h-screen bg-[#FDFBF7] text-[#3E2723] font-serif flex flex-col items-center py-10 px-4">
      <header className="mb-8 text-center max-w-2xl">
        <h1 className="text-4xl md:text-5xl font-bold mb-3 text-[#2D1B15] tracking-tight" style={{ fontFamily: 'Georgia, serif' }}>
          灵岩谱曲台
        </h1>
        <p className="text-[#5D4037] text-sm md:text-base leading-relaxed" style={{ fontFamily: 'Georgia, serif' }}>在下方五线谱上绘制主旋律后，系统会将音符吸附到敦煌音阶（1-2-3-♯4-5-6）与节奏网格，并通过 AI 后端生成可直接试听的四声部和声建议。</p>
      </header>

      <div className="w-full max-w-6xl flex-1 flex flex-col items-center gap-8">
        <ControlBar 
          onHarmonize={handleHarmonize} 
          onClear={handleClear} 
          onPlay={handlePlay}
          onRecord={handleRecord}
          isGenerating={isGenerating} 
          isPlaying={isPlaying}
          isCountingIn={isCountingIn}
          isRecording={isRecording}
        />

        <TransportBar
          mode={transportMode}
          totalSteps={TOTAL_STEPS}
          activeStep={activeStep}
          countInBeat={countInBeat}
          detectText={detectText}
        />
        
        <div className="w-full overflow-x-auto pb-8 flex justify-center">
          <ScoreGrid 
            notes={notes} 
            onGridClick={handleGridClick} 
            onDrawEnd={handleDrawEnd}
            totalSteps={TOTAL_STEPS} 
            totalPitches={TOTAL_PITCHES} 
            activeStep={activeStep}
            mode={transportMode}
          />
        </div>
      </div>
      
      <footer className="mt-auto pt-8 text-[#8D6E63] text-xs text-center" style={{ fontFamily: 'Georgia, serif' }}>灵岩谱曲台 - Lingyan Composing Platform | 基于 1-2-3-♯4-5-6 敦煌音阶体系</footer>
    </div>
  );
}

export default App;
