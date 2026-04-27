export type Voice = 'user' | 'alto' | 'tenor' | 'bass';

export type Note = {
  id: string;
  pitch: number;
  step: number;
  voice: Voice;
};
