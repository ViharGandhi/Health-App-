import { notFound } from 'next/navigation';
import SleepAnalyticsDetail from '@/components/SleepAnalyticsDetail';

export default async function SleepMetricPage({ params }: { params: Promise<{ metric: string }> }) {
  const { metric } = await params;
  if (!['performance', 'hours-needed', 'hours-needed-percentage', 'restorative', 'time-in-bed'].includes(metric)) notFound();
  return <SleepAnalyticsDetail slug={metric} />;
}
