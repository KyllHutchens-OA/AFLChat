import { useState, useEffect } from 'react';

interface CountdownProps {
  targetDate: string; // ISO date string
}

interface TimeLeft {
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
}

const Countdown: React.FC<CountdownProps> = ({ targetDate }) => {
  const [timeLeft, setTimeLeft] = useState<TimeLeft | null>(null);

  useEffect(() => {
    const calculateTimeLeft = (): TimeLeft | null => {
      const difference = +new Date(targetDate) - +new Date();

      if (difference > 0) {
        return {
          days: Math.floor(difference / (1000 * 60 * 60 * 24)),
          hours: Math.floor((difference / (1000 * 60 * 60)) % 24),
          minutes: Math.floor((difference / 1000 / 60) % 60),
          seconds: Math.floor((difference / 1000) % 60),
        };
      }

      return null;
    };

    // Initial calculation
    setTimeLeft(calculateTimeLeft());

    // Update every second
    const timer = setInterval(() => {
      setTimeLeft(calculateTimeLeft());
    }, 1000);

    return () => clearInterval(timer);
  }, [targetDate]);

  if (!timeLeft) {
    return (
      <div className="text-afl-warm-500">
        Game starting soon...
      </div>
    );
  }

  return (
    <div className="flex gap-4 justify-center">
      {timeLeft.days > 0 && (
        <div className="flex flex-col items-center">
          <div className="text-4xl font-semibold text-afl-accent tabular-nums">
            {timeLeft.days}
          </div>
          <div className="text-sm text-afl-warm-500 mt-1">
            {timeLeft.days === 1 ? 'Day' : 'Days'}
          </div>
        </div>
      )}

      <div className="flex flex-col items-center">
        <div className="text-4xl font-semibold text-afl-accent tabular-nums">
          {String(timeLeft.hours).padStart(2, '0')}
        </div>
        <div className="text-sm text-afl-warm-500 mt-1">Hours</div>
      </div>

      <div className="text-4xl text-afl-warm-300 self-center -mt-6">:</div>

      <div className="flex flex-col items-center">
        <div className="text-4xl font-semibold text-afl-accent tabular-nums">
          {String(timeLeft.minutes).padStart(2, '0')}
        </div>
        <div className="text-sm text-afl-warm-500 mt-1">Minutes</div>
      </div>

      <div className="text-4xl text-afl-warm-300 self-center -mt-6">:</div>

      <div className="flex flex-col items-center">
        <div className="text-4xl font-semibold text-afl-accent tabular-nums">
          {String(timeLeft.seconds).padStart(2, '0')}
        </div>
        <div className="text-sm text-afl-warm-500 mt-1">Seconds</div>
      </div>
    </div>
  );
};

export default Countdown;
