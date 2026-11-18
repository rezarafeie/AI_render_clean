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

export type Segment = {id: string; start: number; end: number; source_in: number; source_out: number; zoom: {from: number; to: number}; zoom_editable: boolean; splittable: boolean;
  effect: string | null; transition: {type: string; frames: number} | null};
export type NativeTimeline = {
  width: number; height: number; crf: number;
  segments: Segment[]; job_id: string; version: number | null; fps: number; duration: number; busy: boolean; arrange: boolean;
  versions: {version: number; source: string}[];
  caption_font: string | null; caption_font_id: string | null;
  layers: {attachment_id: string | null; source_in: number; caption_style: CaptionStyle; highlight: string; kind: LayerKind; index: number; start: number; end: number; label: string; position: "top" | "bottom"; volume_db: number}[];
};
export type SegmentChange = {version: number | null} & (
  {operation: "trim"; segment_id: string; start: number; end: number}
  | {operation: "remove_range"; start: number; end: number}
  | {operation: "restore"; restore_version: number}
  | {operation: "split"; segment_id: string; start: number}
  | {operation: "duplicate"; segment_id: string}
  | {operation: "zoom"; segment_id: string; zoom_from: number; zoom_to: number}
  | {operation: "move"; segment_id: string; target_id: string; after: boolean}
);

export type CaptionStyle = "normal" | "emphasis" | "cta" | "cover";
export type LayerKind = "caption" | "broll" | "music" | "sfx";
export type LayerChange = {
  version: number | null; kind: LayerKind; operation: "add" | "remove" | "replace";
  attachment_id?: string; source_in?: number; caption_style?: CaptionStyle; highlight?: string;
  index?: number; text?: string; filename?: string; start?: number; end?: number;
  volume_db?: number; position?: "top" | "bottom";
};


export type ResourceChange = {version: number | null; kind: "effect" | "transition"; resource_id: string; targets: string[];
  settings: {duration_frames: number; direction?: "left" | "right" | "up" | "down"; intensity?: number;
    zoom_mode?: "zoom_in" | "zoom_out"; zoom_scale?: number}};

export type CaptionFont = {family: string; style: string; caption_font_id?: string};
