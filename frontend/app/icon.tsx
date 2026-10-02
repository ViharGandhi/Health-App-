import { ImageResponse } from 'next/og';

export const size = { width: 512, height: 512 };
export const contentType = 'image/png';

export default function Icon() {
  return new ImageResponse(
    <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0B0B0B', borderRadius: 108 }}>
      <div style={{ width: 278, height: 278, border: '58px solid #FFFFFF', borderRadius: '50%' }} />
    </div>,
    size,
  );
}
