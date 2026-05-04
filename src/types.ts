export type Voice = 'user' | 'alto' | 'tenor' | 'bass' | 'xiao' | 'pipa' | 'guqin' | 'percussion';

export type NoteDuration = number;

export type Note = {
  id: string;
  pitch: number;
  step: number;
  duration: NoteDuration;
  voice: Voice;
};
