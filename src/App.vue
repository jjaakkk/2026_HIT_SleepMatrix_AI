<script setup lang="ts">
// Phase 1 占位页：数据读取层已就绪，Phase 2-6 将逐步替换为本页结构
const phases = [
  { id: 1, name: '读取数据（txt/json 解析 + 标注 + 指标）', status: 'done' },
  { id: 2, name: '静态热力图（Canvas + turbo 色带）', status: 'todo' },
  { id: 3, name: '帧动画（回放引擎）', status: 'todo' },
  { id: 4, name: '实时指标卡与曲线', status: 'todo' },
  { id: 5, name: '区域分析叠加', status: 'todo' },
  { id: 6, name: '完整大屏 UI', status: 'todo' },
  { id: 7, name: '气囊模块（模拟 + 预留接口）', status: 'todo' },
  { id: 8, name: '最终 Demo', status: 'todo' },
] as const
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <h1>智能床垫实时监测系统</h1>
      <div class="badges">
        <span class="badge replay">● 回放 · 本地历史数据</span>
        <span class="badge">v0.1.0 · Phase 1</span>
      </div>
    </header>
    <main class="content">
      <section class="panel">
        <h2>开发进度</h2>
        <ul class="phases">
          <li v-for="p in phases" :key="p.id" :class="p.status">
            <span class="dot"></span>
            <span>Phase {{ p.id }}：{{ p.name }}</span>
            <span class="tag">{{ p.status === 'done' ? '已完成' : '未开始' }}</span>
          </li>
        </ul>
        <p class="hint">
          数据事实基线：44×24 压力矩阵 · 帧间空行分隔 · 镜像增强帧已识别 ·
          region/spine 标注解析就绪（详见 docs/ 设计文档 v1.3）
        </p>
      </section>
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
}
.topbar h1 {
  font-size: 20px;
  font-weight: 600;
}
.badges {
  display: flex;
  gap: 10px;
}
.badge {
  font-size: 13px;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 12px;
}
.badge.replay {
  color: var(--accent);
  border-color: var(--accent);
}
.content {
  flex: 1;
  padding: 24px;
  display: flex;
  justify-content: center;
}
.panel {
  width: 720px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px 24px;
}
.panel h2 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 14px;
}
.phases {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.phases li {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: var(--text-secondary);
}
.phases li.done {
  color: var(--text);
}
.phases .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-secondary);
  flex: none;
}
.phases li.done .dot {
  background: var(--accent);
  box-shadow: 0 0 6px var(--accent);
}
.phases .tag {
  margin-left: auto;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 8px;
}
.hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}
</style>
