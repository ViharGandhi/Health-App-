import { ImageResponse } from 'next/og';

export const size = { width: 180, height: 180 };
export const contentType = 'image/png';

export default function AppleIcon() {
  return new ImageResponse(
    <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0B0B0B', borderRadius: 38 }}>
      <div style={{ width: 98, height: 98, border: '20px solid #FFFFFF', borderRadius: '50%' }} />
    </div>,
    size,
  );
}
