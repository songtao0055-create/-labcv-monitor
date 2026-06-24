<template>
  <view class="page">
    <!-- 概览卡片 -->
    <view class="overview-grid">
      <view class="ov-card">
        <text class="ov-value">--</text>
        <text class="ov-label">今日告警</text>
      </view>
      <view class="ov-card">
        <text class="ov-value">--</text>
        <text class="ov-label">数据点/小时</text>
      </view>
      <view class="ov-card">
        <text class="ov-value">--</text>
        <text class="ov-label">异常数据点</text>
      </view>
      <view class="ov-card">
        <text class="ov-value">--</text>
        <text class="ov-label">系统在线率</text>
      </view>
    </view>

    <!-- 图表占位 -->
    <view class="chart-card">
      <text class="card-title">📈 测试数据趋势（待接入）</text>
      <view class="chart-placeholder">
        <text class="chart-icon">📊</text>
        <text class="chart-text">接入测试数据 API 后将展示趋势图</text>
        <text class="chart-sub">需后端提供 GET /api/data/trend 接口</text>
      </view>
    </view>

    <!-- 阈值合理性分析 -->
    <view class="card">
      <text class="card-title">🎯 阈值合理性分析</text>
      <view class="threshold-placeholder">
        <text class="ph-text">接入时序数据后将展示：</text>
        <text class="ph-item">• 历史数据分布 (P1/P5/P95/P99)</text>
        <text class="ph-item">• 当前阈值覆盖率</text>
        <text class="ph-item">• 阈值收紧/放宽建议</text>
      </view>
    </view>

    <!-- 异常检测 -->
    <view class="card">
      <text class="card-title">🔍 异常检测 (3σ)</text>
      <view class="empty-small">接入数据流后实时展示异常点</view>
    </view>
  </view>
</template>

<script setup>
// 数据看板 —— 当前为占位页面
// 需要后端提供:
//   GET /api/data/overview  — 概览统计
//   GET /api/data/trend     — 趋势数据 (用于 ECharts)
//   GET /api/data/anomalies — 异常数据点
//   GET /api/data/threshold — 阈值分析报告
</script>

<style lang="scss" scoped>
.page { padding: $spacing-md; min-height: 100vh; }

.overview-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: $spacing-sm; margin-bottom: $spacing-md; }
.ov-card {
  padding: $spacing-md; background: $bg-card; border-radius: $radius-md; text-align: center;
}
.ov-value { font-size: 48rpx; font-weight: 700; color: $accent; display: block; }
.ov-label { font-size: 22rpx; color: $text-muted; margin-top: 4rpx; display: block; }

.card {
  background: $bg-card; border-radius: $radius-lg; padding: $spacing-lg; margin-bottom: $spacing-md;
}
.card-title { font-size: 28rpx; font-weight: 600; display: block; margin-bottom: $spacing-md; }

.chart-placeholder {
  text-align: center; padding: $spacing-xl 0;
}
.chart-icon { font-size: 64rpx; display: block; }
.chart-text { font-size: 26rpx; color: $text-secondary; display: block; margin-top: $spacing-sm; }
.chart-sub { font-size: 22rpx; color: $text-muted; display: block; margin-top: 4rpx; }

.threshold-placeholder { padding: $spacing-sm 0; }
.ph-text { font-size: 26rpx; color: $text-secondary; display: block; margin-bottom: $spacing-sm; }
.ph-item { font-size: 24rpx; color: $text-muted; display: block; padding: 4rpx 0; }

.empty-small { text-align: center; color: $text-muted; font-size: 24rpx; padding: $spacing-md; }
</style>
