const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LONG_MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function formatPlaytime(seconds) {
  const minutes = Math.floor(Math.max(0, seconds) / 60);
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${String(minutes % 60).padStart(2, "0")}m`;
}

export function shortDuration(seconds) {
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;

  if (hours && rest) {
    return `${hours}h ${rest}m`;
  }
  return hours ? `${hours}h` : `${rest}m`;
}

export function exactDuration(seconds) {
  return seconds >= 3600 ? formatPlaytime(seconds) : `${Math.floor(seconds / 60)}m`;
}

export function monthName(date) {
  return LONG_MONTHS[date.getMonth()];
}

export function shortMonth(date) {
  return MONTHS[date.getMonth()];
}

export function weekday(date) {
  return WEEKDAYS[date.getDay()];
}

export function shortDate(date, today = new Date()) {
  const label = `${date.getDate()} ${MONTHS[date.getMonth()]}`;
  return date.getFullYear() === today.getFullYear() ? label : `${label} ${date.getFullYear()}`;
}

export function midnight(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function addDays(date, days) {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + days);
  return copy;
}

export function isoDay(date) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function parseDay(text) {
  const [year, month, day] = text.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function lastPlayed(timestamp) {
  if (!timestamp) {
    return "";
  }
  const day = midnight(new Date(timestamp * 1000));
  const today = midnight(new Date());
  const delta = Math.round((today - day) / 86400000);

  if (delta <= 0) {
    return "today";
  }
  if (delta === 1) {
    return "yesterday";
  }
  if (delta < 7) {
    return `${delta} days ago`;
  }
  return shortDate(day, today);
}

export function capitalize(text) {
  return text ? text[0].toUpperCase() + text.slice(1) : "";
}

export function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}
