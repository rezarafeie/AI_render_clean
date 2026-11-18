export type Engine = "talking" | "localize" | "motion" | "vox" | "story" | "product" | "clips";
export type PanelMode = "manual" | "assisted" | "auto";
export type Setup = {
  title: string; engine: Engine; mode: PanelMode; style: string;
  topic: string; aspect: "source" | "vertical" | "square" | "landscape"; seconds: 15 | 30 | 45 | 60; source_url: string; attachment_ids: string[];
};
export type Capabilities = { talking_styles: {id: string; label: string}[]; claude_motion: boolean };
export type SpeechWord = {text: string; start: number; end: number};
export type PanelTranscript = {
  source_job: string; editable: boolean; version_id: string | null;
  sentences: (SpeechWord & {id: number; dropped: boolean; words: SpeechWord[]})[];
};

export type Segment = {id: string; start: number; end: number; source_in: number; source_out: number};
export type NativeTimeline = {
  segments: Segment[]; job_id: string; version: number | null; fps: number; duration: number; busy: boolean; arrange: boolean;
  versions: {version: number; source: string}[];
  layers: {kind: LayerKind; index: number; start: number; end: number; label: string; position: "top" | "bottom"; volume_db: number}[];
};
export type SegmentChange = {version: number | null} & (
  {operation: "trim"; segment_id: string; start: number; end: number}
  | {operation: "remove_range"; start: number; end: number}
  | {operation: "restore"; restore_version: number}
  | {operation: "split"; segment_id: string; start: number}
  | {operation: "duplicate"; segment_id: string}
  | {operation: "move"; segment_id: string; target_id: string; after: boolean}
);

export type LayerKind = "caption" | "broll" | "music" | "sfx";
export type LayerChange = {
  version: number | null; kind: LayerKind; operation: "add" | "remove" | "replace";
  index?: number; text?: string; filename?: string; start?: number; end?: number;
  volume_db?: number; position?: "top" | "bottom";
};
