import { el, svg } from "../dom.js";
import { exactDuration, shortDuration } from "../format.js";

const HEIGHT = 190;
const PAD_LEFT = 46;
const PAD_RIGHT = 6;
const PAD_TOP = 18;
const PAD_BOTTOM = 22;
const MAX_BAR = 24;

const TICK_STEPS = [5, 10, 15, 30, 60, 120, 180, 240, 360, 480, 720, 1440].map((m) => m * 60);

function tickStep(peak) {
  for (const step of TICK_STEPS) {
    if (peak <= step * 4) {
      return step;
    }
  }
  const biggest = TICK_STEPS[TICK_STEPS.length - 1];
  return biggest * Math.max(1, Math.ceil(peak / (biggest * 4)));
}

export function drawChart(container, points) {
  container.chartPoints = points;

  if (!container.chartObserver) {
    let lastWidth = 0;
    container.chartObserver = new ResizeObserver(() => {
      if (container.clientWidth !== lastWidth) {
        lastWidth = container.clientWidth;
        render(container, container.chartPoints);
      }
    });
    container.chartObserver.observe(container);
  }
  render(container, points);
}

function render(container, points) {
  const WIDTH = Math.max(300, container.clientWidth || 600);
  const peak = Math.max(0, ...points.map((p) => p.seconds));
  const step = tickStep(peak);
  const ceiling = peak ? Math.max(step, Math.ceil(peak / step) * step) : step;

  const base = HEIGHT - PAD_BOTTOM;
  const y = (seconds) => base - ((base - PAD_TOP) * seconds) / ceiling;
  const slot = (WIDTH - PAD_LEFT - PAD_RIGHT) / points.length;
  const barWidth = Math.max(2, Math.min(MAX_BAR, slot - 2));

  const chart = svg("svg", { viewBox: `0 0 ${WIDTH} ${HEIGHT}` });

  for (let value = 0; value <= ceiling; value += step) {
    chart.append(svg("line", { x1: PAD_LEFT, x2: WIDTH - PAD_RIGHT, y1: y(value), y2: y(value) }));
    chart.append(
      svg("text", { x: PAD_LEFT - 6, y: y(value) + 3, "text-anchor": "end" }, shortDuration(value)),
    );
  }

  const tip = el("div", { class: "chart-tip", hidden: true });
  const peakIndex = peak ? points.findIndex((p) => p.seconds === peak) : -1;

  points.forEach((point, i) => {
    const center = PAD_LEFT + slot * (i + 0.5);

    if (point.axis) {
      const anchor = i === points.length - 1 ? "end" : "middle";
      chart.append(svg("text", { x: center, y: HEIGHT - 6, "text-anchor": anchor }, point.axis));
    }

    if (point.seconds > 0) {
      const top = y(point.seconds);
      const column = svg("rect", {
        class: "bar-column",
        x: center - barWidth / 2,
        y: top,
        width: barWidth,
        height: base - top,
        rx: Math.min(4, barWidth / 2),
      });
      chart.append(column);

      if (i === peakIndex) {
        chart.append(
          svg(
            "text",
            { class: "peak", x: center, y: top - 6, "text-anchor": "middle" },
            shortDuration(point.seconds),
          ),
        );
      }
    }

    const hit = svg("rect", {
      x: PAD_LEFT + slot * i,
      y: 0,
      width: slot,
      height: HEIGHT,
      fill: "transparent",
    });
    hit.addEventListener("mouseenter", () => {
      const read = point.seconds ? exactDuration(point.seconds) : "nothing read";
      tip.textContent = `${point.tip}  ·  ${read}`;
      tip.style.left = `${(center / WIDTH) * 100}%`;
      tip.hidden = false;
    });
    hit.addEventListener("mouseleave", () => (tip.hidden = true));
    chart.append(hit);
  });

  if (!peak) {
    const middle = (PAD_TOP + base) / 2;
    chart.append(
      svg(
        "text",
        { x: WIDTH / 2, y: middle, "text-anchor": "middle" },
        "Nothing read in this period",
      ),
    );
  }

  container.replaceChildren(el("div", { class: "chart" }, chart, tip));
}
