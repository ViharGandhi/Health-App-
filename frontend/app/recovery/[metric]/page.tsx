import { notFound } from 'next/navigation';
import RecoveryTrendDetail from '@/components/RecoveryTrendDetail';
import { recoveryMetrics } from '@/lib/recovery';

export default async function RecoveryMetricPage({ params }: { params: Promise<{ metric: string }> }) {
  const { metric } = await params;
  if (!recoveryMetrics.some(item => item.slug === metric)) notFound();
  return <RecoveryTrendDetail slug={metric} />;
}
