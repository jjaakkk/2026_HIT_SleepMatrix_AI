/**
 * 回放引擎：帧序列播放控制（纯逻辑，不依赖 DOM，便于单元测试）。
 *
 * 说明：动态文件约 70 秒 159 帧（采集帧率 ≈ 2.3 fps），静态动作 15/30 帧。
 * 为演示效果，默认以 10 fps 基准回放（0.5/1/2/4× 倍速），界面如实标注。
 */
export interface PlaybackOptions {
  /** 基准回放帧率（默认 10 fps） */
  fps?: number;
  /** 播到末尾后是否循环（默认 false，停在最后一帧） */
  loop?: boolean;
}

export type PlaybackPhase = 'idle' | 'playing' | 'paused' | 'ended';

export class PlaybackController {
  readonly frames: ReadonlyArray<ArrayLike<number>>;
  readonly fps: number;
  readonly loop: boolean;

  private index = 0;
  private phase: PlaybackPhase = 'idle';
  private speedValue = 1;
  /** 当前帧已累计的播放时长（ms，×速度后） */
  private elapsed = 0;

  /** 帧切换回调（含 seek） */
  onFrame: ((index: number) => void) | null = null;
  /** 播放到末尾（loop=false 时）或结束事件 */
  onEnd: ((index: number) => void) | null = null;

  constructor(frames: ReadonlyArray<ArrayLike<number>>, opts: PlaybackOptions = {}) {
    if (frames.length === 0) throw new Error('回放帧序列不能为空');
    this.frames = frames;
    this.fps = opts.fps ?? 10;
    this.loop = opts.loop ?? false;
  }

  get frameIndex(): number {
    return this.index;
  }
  get frameCount(): number {
    return this.frames.length;
  }
  get isPlaying(): boolean {
    return this.phase === 'playing';
  }
  get phaseValue(): PlaybackPhase {
    return this.phase;
  }
  get speed(): number {
    return this.speedValue;
  }
  set speed(v: number) {
    if (![0.5, 1, 2, 4].includes(v)) throw new Error(`不支持的倍速：${v}`);
    this.speedValue = v;
  }

  play(): void {
    if (this.phase === 'playing') return;
    if (this.phase === 'ended' && this.index >= this.frameCount - 1) {
      this.index = 0; // 播完后重新播放 → 从头开始
      this.onFrame?.(this.index);
    }
    this.phase = 'playing';
    this.elapsed = 0;
  }

  pause(): void {
    if (this.phase === 'playing') this.phase = 'paused';
  }

  toggle(): void {
    if (this.phase === 'playing') this.pause();
    else this.play();
  }

  /** 单步（±1），步进时进入暂停态 */
  step(delta: 1 | -1): void {
    this.phase = 'paused';
    this.seek(this.index + delta);
  }

  /** 跳转到指定帧（clamp 到有效范围） */
  seek(i: number): void {
    const next = Math.min(Math.max(Math.round(i), 0), this.frameCount - 1);
    if (next !== this.index) {
      this.index = next;
      this.elapsed = 0;
      if (this.phase === 'ended' && next < this.frameCount - 1) this.phase = 'paused';
      this.onFrame?.(next);
    }
  }

  /**
   * 时间推进（毫秒）。由 requestAnimationFrame 循环调用。
   * 已累计时长超过单帧时长（按倍速折算）则前进一帧（可多帧）。
   * 单次 tick 最多前进 8 帧：渲染掉帧时回放仍按真实时钟追赶，同时避免
   * 后台切回时一次性跳过过多帧。
   */
  tick(dtMs: number): void {
    if (this.phase !== 'playing' || dtMs <= 0) return;
    const frameMs = 1000 / this.fps;
    this.elapsed = Math.min(this.elapsed + dtMs * this.speedValue, frameMs * 8);
    while (this.elapsed >= frameMs) {
      this.elapsed -= frameMs;
      if (this.index < this.frameCount - 1) {
        this.index++;
        this.onFrame?.(this.index);
      } else {
        if (this.loop) {
          this.index = 0;
          this.onFrame?.(this.index);
        } else {
          this.phase = 'ended';
          this.onEnd?.(this.index);
          this.elapsed = 0;
          break;
        }
      }
    }
  }
}
