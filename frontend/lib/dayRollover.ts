export function watchDayChange(onChange: () => void) {
  let day = new Date().toDateString();
  let timer: ReturnType<typeof setTimeout>;
  const check = () => {
    const now = new Date();
    if (now.toDateString() !== day) {
      day = now.toDateString();
      onChange();
    }
    clearTimeout(timer);
    const midnight = new Date(now);
    midnight.setHours(24, 0, 0, 0);
    timer = setTimeout(check, midnight.getTime() - now.getTime());
  };
  const returned = () => { if (!document.hidden) check(); };
  check();
  window.addEventListener('focus', returned);
  document.addEventListener('visibilitychange', returned);
  return () => {
    clearTimeout(timer);
    window.removeEventListener('focus', returned);
    document.removeEventListener('visibilitychange', returned);
  };
}
