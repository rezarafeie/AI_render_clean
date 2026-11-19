import React from "react";
import type {NativeTimeline} from "./types";

const formats: [string, number, number][] = [
  ["عمودی · ۷۲۰p", 720, 1280], ["عمودی · ۱۰۸۰p", 1080, 1920],
  ["مربعی · ۴۸۰p", 480, 480], ["مربعی · ۱۰۸۰p", 1080, 1080],
  ["افقی · ۷۲۰p", 1280, 720], ["افقی · ۱۰۸۰p", 1920, 1080],
];
const qualities: [string, number][] = [["کم‌حجم", 26], ["استاندارد", 20], ["کیفیت بالا", 16]];

export function NativeExport({data, disabled, onSave}: {
  data: NativeTimeline; disabled: boolean; onSave: (config: {width: number; height: number; crf: number}) => Promise<boolean>;
}) {
  const initial = `${data.width}x${data.height}`;
  const [size, setSize] = React.useState(initial);
  const [quality, setQuality] = React.useState(data.crf);
  return <fieldset className="mp-reset" disabled={disabled}>
    <div className="mp-form-grid">
      <label>اندازهٔ خروجی<select className="input" value={size} onChange={e => setSize(e.target.value)}>
        <option value={initial}>اندازهٔ فعلی · {data.width} × {data.height}</option>
        {formats.filter(([, w, h]) => `${w}x${h}` !== initial).map(([label, w, h]) =>
          <option key={label} value={`${w}x${h}`}>{label}</option>)}
      </select></label>
      <label>کیفیت فایل<select className="input" value={quality} onChange={e => setQuality(Number(e.target.value))}>
        {!qualities.some(([, crf]) => crf === data.crf) && <option value={data.crf}>تنظیم فعلی · CRF {data.crf}</option>}
        {qualities.map(([label, crf]) => <option key={crf} value={crf}>{label}</option>)}
      </select></label>
    </div>
    <p className="mp-muted">{data.fps} فریم بر ثانیه · با تغییر نسبت تصویر، کادربندی خروجی عوض می‌شود.</p>
    <button className="btn btn-secondary" disabled={size === initial && quality === data.crf} onClick={() => {
      const [width, height] = size.split("x").map(Number);
      void onSave({width, height, crf: quality});
    }}>ذخیرهٔ تنظیمات خروجی</button>
  </fieldset>;
}
