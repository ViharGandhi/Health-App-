import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'Ojas — Health and Recovery',
    short_name: 'Ojas',
    description: 'Personal Fitbit health trends and recovery signals.',
    start_url: '/',
    display: 'standalone',
    background_color: '#0B0B0B',
    theme_color: '#0B0B0B',
    icons: [{ src: '/icon', sizes: '512x512', type: 'image/png' }],
  };
}
