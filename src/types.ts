export type Voice = 'user' | 'alto' | 'tenor' | 'bass' | 'xiao' | 'pipa' | 'guqin' | 'percussion';

export type NoteDuration = number;

export type Note = {
  id: string;
  pitch: number;
  step: number;
  duration: NoteDuration;
  voice: Voice;
};

export type ArrangementPhase = {
  index: number;
  label: string;
  bars: number;
  voices: Voice[];
  notes: Note[];
};
