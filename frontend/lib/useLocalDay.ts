'use client';

import { useEffect, useState } from 'react';
import { localDay } from './recovery';
import { watchDayChange } from './dayRollover';

export function useLocalDay() {
  const [day, setDay] = useState(localDay);
  useEffect(() => {
    setDay(localDay());
    return watchDayChange(() => setDay(localDay()));
  }, []);
  return day;
}
