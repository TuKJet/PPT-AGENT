from pathlib import Path
import io
import json
import re
from pptx import Presentation
from pptx.util import Inches
from playwright_runtime import launch_global_chromium, sync_playwright

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)


COMPACT_STYLE = """
.slide {
  gap: 12px !important;
  padding: 16px 18px 14px 18px !important;
}
.header {
  gap: 6px !important;
  max-height: 104px !important;
}
.title {
  font-size: 30px !important;
  line-height: 1.15 !important;
}
.subtitle {
  font-size: 13px !important;
  line-height: 1.2 !important;
}
.card,
.summary-card,
.footer-card {
  padding: 14px 16px !important;
}
.card-inner {
  padding: 14px 16px !important;
}
.card-title,
.mini-title,
.side-title,
.panel-title {
  font-size: 19px !important;
  line-height: 1.18 !important;
  margin-bottom: 10px !important;
}
.step,
.stage,
.launch-box {
  padding: 12px !important;
}
.timeline-card {
  justify-content: flex-start !important;
  gap: 10px !important;
}
.flow,
.summary,
.decision-steps,
.interest-grid,
.top-right,
.bottom-right,
.timeline,
.main,
.platforms,
.tags,
.stage-tags {
  gap: 10px !important;
}
.metric-main {
  gap: 12px !important;
  margin: 8px 0 8px !important;
}
.num-block {
  padding: 12px 12px 10px !important;
}
.tag,
.pill,
.platform {
  font-size: 11px !important;
  padding: 5px 9px !important;
}
.footer,
.summary-card,
.footer-card {
  height: 84px !important;
  min-height: 84px !important;
}
.summary-quote,
.footer-key {
  font-size: 22px !important;
  line-height: 1.15 !important;
}
.summary-sub,
.footer-text,
.metric-desc,
.step-text,
.stage-desc,
.panel-desc,
.launch-text,
.accept-line,
.lead,
.box-sub,
.metric-sub,
.mini-text {
  font-size: 13px !important;
  line-height: 1.35 !important;
}
.metric,
.metric-big,
.metric.small,
.launch-date,
.num {
  font-size: 32px !important;
  line-height: 1 !important;
}
.step-num,
.icon {
  transform: scale(0.92);
  transform-origin: center;
}
"""


TOC_SAFE_STYLE = """
.slide {
  gap: 14px !important;
}
.left-card {
  justify-content: flex-start !important;
  gap: 16px !important;
}
.flow-card {
  gap: 12px !important;
}
.steps {
  flex: 1 !important;
  gap: 12px !important;
}
.flow-fill {
  display: grid !important;
  grid-template-columns: repeat(3, 1fr) !important;
  gap: 12px !important;
  margin-top: 2px !important;
}
.fill-card {
  border-radius: 12px !important;
  padding: 12px 12px 10px !important;
  background: rgba(255,255,255,0.03) !important;
  border: 1px solid rgba(122, 137, 165, 0.14) !important;
}
.fill-label {
  font-size: 12px !important;
  font-weight: 800 !important;
  color: #8FA3BF !important;
  margin-bottom: 6px !important;
  letter-spacing: 0.3px !important;
  text-transform: uppercase !important;
}
.fill-text {
  font-size: 13px !important;
  line-height: 1.4 !important;
  color: #C5CFDC !important;
}
"""


STEP_CARD_SAFE_STYLE = """
.steps,
.process-grid,
.process-wrap {
  gap: 8px !important;
}
.step {
  grid-template-columns: 40px 1fr !important;
  gap: 8px !important;
  padding: 10px !important;
  min-width: 0 !important;
}
.step-num,
.step-no {
  width: 40px !important;
  height: 40px !important;
  font-size: 18px !important;
  border-radius: 10px !important;
  flex: 0 0 40px !important;
}
.step-body,
.step-head {
  gap: 3px !important;
  min-width: 0 !important;
}
.step-title,
.step h4 {
  font-size: 16px !important;
  line-height: 1.12 !important;
  overflow-wrap: anywhere !important;
  word-break: break-word !important;
}
.step-text,
.step-desc,
.step p,
.card-sub,
.mini-note {
  font-size: 12px !important;
  line-height: 1.26 !important;
  overflow-wrap: anywhere !important;
  word-break: break-word !important;
}
.step-note,
.step-time {
  font-size: 11px !important;
  line-height: 1.15 !important;
}
.split,
.mini-tags,
.step-tags {
  gap: 6px !important;
}
.mini-tag,
.pill-green,
.pill-red,
.step-tag {
  font-size: 11px !important;
  padding: 4px 8px !important;
}
"""


CONCLUSION_SAFE_STYLE = """
.slide {
  grid-template-rows: 92px 1fr 84px !important;
  gap: 12px !important;
  padding: 16px 18px 16px 18px !important;
}
.main {
  grid-template-columns: 1.08fr 0.92fr !important;
  gap: 16px !important;
}
.card {
  padding: 18px !important;
}
.mid-bridge {
  padding: 12px 14px !important;
  gap: 10px !important;
}
.bridge-label {
  font-size: 12px !important;
  padding: 5px 9px !important;
}
.bridge-item {
  font-size: 13px !important;
  line-height: 1.3 !important;
}
.arrow {
  font-size: 16px !important;
}
.steps {
  gap: 10px !important;
}
.step {
  grid-template-columns: 44px 1fr !important;
  gap: 10px !important;
  padding: 12px !important;
}
.step-num {
  font-size: 22px !important;
  border-radius: 10px !important;
}
.step-body {
  gap: 4px !important;
}
.step-title {
  font-size: 17px !important;
  line-height: 1.15 !important;
}
.step-desc {
  font-size: 13px !important;
  line-height: 1.32 !important;
}
.step-note {
  font-size: 11px !important;
}
.split-result {
  padding: 12px 14px !important;
  gap: 10px !important;
}
.result-box {
  padding: 10px 12px !important;
  gap: 5px !important;
}
.result-box strong {
  font-size: 15px !important;
  line-height: 1.15 !important;
}
.result-box p {
  font-size: 12px !important;
  line-height: 1.28 !important;
}
.footer {
  height: 84px !important;
}
.summary-card {
  padding: 12px 16px !important;
  gap: 14px !important;
}
.summary-pill {
  font-size: 11px !important;
  padding: 7px 10px !important;
}
.summary-text {
  font-size: 16px !important;
  line-height: 1.25 !important;
}
.summary-actions {
  gap: 8px !important;
}
.choice {
  font-size: 11px !important;
  padding: 8px 10px !important;
}
"""


SUMMARY_SAFE_STYLE = """
.slide {
  grid-template-rows: auto 1fr 84px !important;
  gap: 12px !important;
  padding: 16px 18px 14px 18px !important;
}
.header,
.title-wrap {
  gap: 6px !important;
}
.title {
  font-size: 30px !important;
  line-height: 1.15 !important;
}
.subtitle {
  font-size: 13px !important;
  line-height: 1.2 !important;
}
.main {
  grid-template-columns: minmax(0, 1.12fr) minmax(0, 0.88fr) !important;
  gap: 12px !important;
}
.mid-card {
  display: none !important;
}
.card,
.card-inner,
.summary-card,
.footer-card {
  padding: 14px 16px !important;
}
.card-title,
.panel-title,
.side-title,
.mini-title {
  font-size: 19px !important;
  line-height: 1.18 !important;
  margin-bottom: 10px !important;
}
.timeline-card {
  justify-content: flex-start !important;
  gap: 10px !important;
}
.interest-grid,
.tags,
.platforms,
.summary,
.decision-steps,
.timeline {
  gap: 10px !important;
}
.metric-main {
  gap: 12px !important;
  margin: 8px 0 8px !important;
}
.num-block {
  padding: 12px 12px 10px !important;
}
.step,
.stage,
.launch-box,
.accept-line {
  padding: 12px !important;
}
.step:nth-child(n+3) {
  display: none !important;
}
.metric-card .accept-line {
  display: none !important;
}
.footer,
.summary-card,
.footer-card {
  height: 84px !important;
  min-height: 84px !important;
}
.summary-quote,
.footer-key {
  font-size: 22px !important;
  line-height: 1.15 !important;
}
.tag,
.pill,
.platform {
  font-size: 11px !important;
  padding: 5px 9px !important;
}
.metric,
.metric-big,
.metric.small,
.launch-date,
.num {
  font-size: 32px !important;
  line-height: 1 !important;
}
.panel-desc,
.step p,
.metric-desc,
.metric-sub,
.launch-text,
.summary-sub,
.footer-text,
.accept-line,
.lead,
.box-sub,
.mini-text {
  font-size: 13px !important;
  line-height: 1.35 !important;
}
"""


TIMELINE_SAFE_STYLE = """
.slide {
  grid-template-rows: 88px 1fr 84px !important;
  gap: 12px !important;
  padding: 16px 18px 14px 18px !important;
}
.header,
.title-wrap {
  gap: 6px !important;
}
h1,
.title {
  font-size: 29px !important;
  line-height: 1.15 !important;
  max-width: 900px !important;
}
.subtitle {
  font-size: 13px !important;
  line-height: 1.2 !important;
}
.header-badge {
  min-width: 168px !important;
  padding: 10px 12px !important;
}
.main {
  grid-template-columns: 1.04fr 0.96fr !important;
  gap: 12px !important;
}
.card,
.metric-card,
.node-card,
.footer-card {
  padding: 16px !important;
}
.card-title,
.metric-title,
.node-name,
.step-title {
  font-size: 18px !important;
  line-height: 1.18 !important;
}
.timeline {
  grid-template-columns: repeat(4, 1fr) !important;
  gap: 8px !important;
}
.timeline .step:nth-child(n+5) {
  display: none !important;
}
.step {
  padding-top: 12px !important;
  min-width: 0 !important;
}
.step-head {
  gap: 6px !important;
  margin-bottom: 8px !important;
  min-width: 0 !important;
}
.step-head .num,
.num {
  width: 22px !important;
  height: 22px !important;
  font-size: 11px !important;
  flex: 0 0 22px !important;
}
.step-title {
  font-size: 14px !important;
  line-height: 1.15 !important;
  overflow-wrap: anywhere !important;
  word-break: break-word !important;
}
.step-body {
  padding-left: 28px !important;
  gap: 4px !important;
  min-width: 0 !important;
}
.step-time {
  font-size: 11px !important;
  line-height: 1.15 !important;
  overflow-wrap: anywhere !important;
  word-break: break-word !important;
}
.step-text,
.node-desc,
.mini-summary p,
.footer-right,
.metric .note {
  font-size: 12px !important;
  line-height: 1.3 !important;
  overflow-wrap: anywhere !important;
  word-break: break-word !important;
}
.right-col {
  grid-template-rows: 1fr 152px !important;
  gap: 12px !important;
}
.highlight-block,
.node-grid,
.tags {
  gap: 10px !important;
}
.metric {
  padding: 14px !important;
}
.metric .number {
  font-size: 32px !important;
  margin-bottom: 4px !important;
}
.footer-card {
  grid-template-columns: 170px 1fr !important;
  gap: 14px !important;
  padding: 12px 16px !important;
}
.footer-left .big {
  font-size: 24px !important;
}
"""


DENSE_CARD_SAFE_STYLE = """
.slide {
  gap: 12px !important;
  padding: 16px 18px 14px 18px !important;
  grid-template-rows: auto 1fr 88px !important;
}
.header,
.title-wrap {
  gap: 6px !important;
}
h1,
.title {
  font-size: 29px !important;
  line-height: 1.14 !important;
}
.subtitle {
  font-size: 13px !important;
  line-height: 1.2 !important;
}
.main,
.side,
.right-col,
.right-grid,
.right-panel,
.stat-grid,
.highlight-block,
.logic-row,
.timeline,
.timeline-wrap,
.node-grid,
.tags,
.mini-tags,
.tag-row,
.summary-tags,
.footer-tags,
.bullet-list,
.support-list,
.process-grid,
.metrics-grid,
.metrics,
.scene-top,
.bottom {
  gap: 8px !important;
}
.card,
.metric-card,
.stats-card,
.evidence-card,
.talk-card,
.node-card,
.footer-card,
.panel,
.memory-card,
.stage,
.summary-card,
.metric-box,
.support-item,
.time-box,
.scene-item,
.policy-box {
  padding: 12px !important;
}
.card-title,
.stats-title,
.metric-title,
.hero-title,
.big-conclusion,
.node-name,
.logic-name,
.step-title,
.memory-title,
.stage-name,
.footer-title,
.section-title,
.support-title {
  font-size: 16px !important;
  line-height: 1.12 !important;
}
.card-label,
.eyebrow,
.source-tag,
.badge-text,
.metric-badge,
.tag,
.mini-tag,
.platform,
.pill,
.memory-kicker,
.stage-label,
.footer-tag,
.step-tag {
  font-size: 10px !important;
}
.hero-desc,
.short-text,
.logic-text,
.node-text,
.node-desc,
.metric-desc,
.metric-sub,
.step-text,
.step-desc,
.note,
.desc,
.support,
.footer-right,
.summary-sub,
.footer-text,
.lead,
.stage-desc,
.summary-text,
.metric-text,
.metric-caption,
.bullet,
.support-text,
.keyline-text,
.card-sub,
.timeline-summary,
.metric-note,
.scene-text,
.policy-title,
.policy-note,
.card-note,
.mini-note {
  font-size: 11px !important;
  line-height: 1.24 !important;
}
.stat,
.metric,
.num-block,
.logic-item,
.node,
.step,
.fromto,
.stage,
.support-item,
.time-box,
.metric-box,
.scene-item,
.policy-box {
  padding: 10px !important;
}
.stat-value,
.stat-num,
.metric .number,
.metric-big,
.metric,
.big,
.stage-year,
.year,
.metric-main,
.big-number,
.metric-number,
.policy-year .big {
  font-size: 26px !important;
  line-height: 1 !important;
}
.step,
.node,
.logic-item,
.card,
.metric-card,
.step-title,
.step-text,
.node-name,
.node-desc,
.logic-name,
.logic-text,
.memory-title,
.footer-right,
.stage,
.stage-name,
.stage-desc,
.summary-text,
.metric-text,
.metric-caption,
.support-text,
.footer-text,
.lead,
.keyline-text,
.card-sub,
.timeline-summary,
.metric-note,
.scene-text,
.policy-title,
.mini-note {
  overflow-wrap: anywhere !important;
  word-break: break-word !important;
}
.step-head .num,
.num,
.step-no {
  width: 22px !important;
  height: 22px !important;
  font-size: 11px !important;
  flex: 0 0 22px !important;
}
.step-head {
  gap: 8px !important;
}
.step-body {
  padding-left: 28px !important;
  gap: 4px !important;
}
.timeline {
  grid-template-columns: repeat(4, 1fr) !important;
}
.timeline .step:nth-child(n+5),
.timeline-wrap .node:nth-child(n+5),
.timeline .node:nth-child(n+5),
.logic-row .logic-item:nth-child(n+4),
.node-grid .node:nth-child(n+5),
.tag-row .tag:nth-child(n+4),
.summary-tags .tag:nth-child(n+4),
.footer-tags .footer-tag:nth-child(n+3),
.tags .tag:nth-child(n+4),
.bullet-list .bullet:nth-child(n+3),
.support-list .support-item:nth-child(n+3),
.metrics-grid .metric-box:nth-child(n+3),
.metrics .metric:nth-child(n+3),
.scene-top .scene-item:nth-child(n+4) {
  display: none !important;
}
.footer,
.summary-card,
.footer-card {
  height: 88px !important;
  min-height: 88px !important;
}
.panel {
  gap: 10px !important;
}
.panel > div[style*="grid-template-rows:1fr 1fr"] {
  grid-template-rows: minmax(0, 1fr) minmax(0, 1fr) !important;
  gap: 10px !important;
  min-height: 0 !important;
}
.panel > div[style*="grid-template-rows:1fr 1fr"] > article {
  padding: 12px !important;
  gap: 4px !important;
  min-height: 0 !important;
}
.panel > div[style*="grid-template-rows:1fr 1fr"] > article > div,
.panel > div[style*="grid-template-rows:1fr 1fr"] > article p,
.panel > div[style*="grid-template-rows:1fr 1fr"] > article span {
  overflow-wrap: anywhere !important;
  word-break: break-word !important;
}
.panel > div[style*="grid-template-rows:1fr 1fr"] > article > div:nth-child(2) {
  font-size: 28px !important;
  line-height: 1 !important;
}
.panel > div[style*="grid-template-rows:1fr 1fr"] > article > div:nth-child(3),
.panel > div[style*="grid-template-rows:1fr 1fr"] > article > div:nth-child(4),
.panel > div[style*="grid-template-rows:1fr 1fr"] > article p {
  font-size: 11px !important;
  line-height: 1.24 !important;
}
.panel > div[style*="display:flex"][style*="flex-wrap:wrap"] {
  gap: 6px !important;
  margin-top: 4px !important;
  align-content: flex-start !important;
}
.panel > div[style*="display:flex"][style*="flex-wrap:wrap"] > span {
  font-size: 10px !important;
  padding: 4px 8px !important;
}
"""


DUAL_PANEL_COVER_SAFE_STYLE = """
.slide {
  gap: 10px !important;
  padding: 14px 16px 12px !important;
  grid-template-rows: auto 1fr 74px !important;
}
.header {
  min-height: 106px !important;
  padding-bottom: 8px !important;
}
.title {
  font-size: 27px !important;
  line-height: 1.08 !important;
}
.subtitle {
  font-size: 12px !important;
  line-height: 1.18 !important;
}
.content {
  grid-template-columns: 1.06fr 0.94fr !important;
  gap: 14px !important;
}
.panel {
  padding: 16px !important;
  border-radius: 20px !important;
}
.hero-left {
  display: grid !important;
  grid-template-rows: auto auto auto !important;
  align-content: start !important;
  justify-content: normal !important;
  gap: 10px !important;
  overflow: hidden !important;
}
.hero-right {
  display: grid !important;
  grid-template-rows: auto auto 1fr !important;
  align-content: start !important;
  gap: 8px !important;
  overflow: hidden !important;
}
.hero-top {
  grid-template-columns: minmax(0, 1fr) 180px !important;
  gap: 10px !important;
}
.hero-kicker {
  padding: 6px 10px !important;
  font-size: 10px !important;
}
.hero-headline {
  margin: 10px 0 8px !important;
  font-size: 23px !important;
  line-height: 1.03 !important;
}
.hero-summary {
  max-width: 100% !important;
  font-size: 11px !important;
  line-height: 1.32 !important;
}
.capability-stack {
  gap: 6px !important;
}
.cap-chip {
  gap: 6px !important;
  padding: 7px 9px !important;
  border-radius: 12px !important;
  font-size: 10px !important;
}
.cap-chip strong,
.cap-chip span {
  font-size: 9px !important;
  line-height: 1.1 !important;
}
.hero-mid {
  margin-top: 0 !important;
  gap: 7px !important;
}
.logic-card {
  grid-template-columns: 68px 1fr !important;
  gap: 9px !important;
  padding: 9px 10px !important;
  border-radius: 15px !important;
}
.logic-index {
  height: 26px !important;
  border-radius: 9px !important;
  font-size: 9px !important;
}
.logic-title {
  margin: 0 0 3px !important;
  font-size: 13px !important;
  line-height: 1.12 !important;
}
.logic-desc {
  font-size: 10px !important;
  line-height: 1.24 !important;
  display: -webkit-box !important;
  -webkit-box-orient: vertical !important;
  -webkit-line-clamp: 2 !important;
  overflow: hidden !important;
}
.hero-bottom {
  padding-top: 0 !important;
  gap: 6px !important;
}
.tag-row {
  gap: 5px !important;
  margin-top: 0 !important;
}
.tag {
  padding: 4px 7px !important;
  font-size: 9px !important;
}
.tag-row .tag:nth-child(n+4) {
  display: none !important;
}
.decision-bar {
  gap: 7px !important;
  padding: 8px 9px !important;
  border-radius: 13px !important;
  align-items: flex-start !important;
}
.decision-label {
  padding: 4px 7px !important;
  font-size: 8px !important;
}
.decision-text {
  font-size: 10px !important;
  line-height: 1.22 !important;
  display: -webkit-box !important;
  -webkit-line-clamp: 2 !important;
  -webkit-box-orient: vertical !important;
  overflow: hidden !important;
}
.metrics-head {
  gap: 8px !important;
}
.metrics-title {
  font-size: 13px !important;
  line-height: 1.1 !important;
}
.metrics-note {
  padding: 4px 7px !important;
  font-size: 9px !important;
}
.metrics-grid {
  gap: 7px !important;
}
.metrics-grid .metric-card:nth-child(n+4) {
  display: none !important;
}
.metric-card {
  min-height: 82px !important;
  padding: 9px 10px !important;
  border-radius: 14px !important;
}
.metric-label {
  font-size: 9px !important;
}
.metric-value {
  margin: 5px 0 3px !important;
  font-size: 22px !important;
}
.metric-desc {
  font-size: 10px !important;
  line-height: 1.22 !important;
  display: -webkit-box !important;
  -webkit-box-orient: vertical !important;
  -webkit-line-clamp: 2 !important;
  overflow: hidden !important;
}
.loop-box {
  padding: 8px 9px !important;
  border-radius: 16px !important;
  gap: 4px !important;
  min-height: 0 !important;
  grid-template-rows: auto auto auto !important;
  align-content: start !important;
}
.loop-title {
  font-size: 12px !important;
  line-height: 1.08 !important;
}
.loop-sub {
  margin-top: 1px !important;
  font-size: 9px !important;
  line-height: 1.14 !important;
  display: -webkit-box !important;
  -webkit-box-orient: vertical !important;
  -webkit-line-clamp: 1 !important;
  overflow: hidden !important;
}
.loop-graphic {
  min-height: 58px !important;
  height: 58px !important;
}
.core-ring {
  width: 88px !important;
  height: 88px !important;
}
.core-ring::before {
  inset: 20px !important;
  font-size: 9px !important;
}
.loop-node {
  padding: 4px 6px !important;
  font-size: 8px !important;
}
.node-top {
  top: 0 !important;
}
.node-right {
  right: -2px !important;
}
.node-bottom {
  bottom: 0 !important;
}
.node-left {
  left: -2px !important;
}
.support-row {
  gap: 4px !important;
}
.support-chip {
  padding: 3px 6px !important;
  font-size: 8px !important;
}
.support-row .support-chip:nth-child(n+4) {
  display: none !important;
}
.footer {
  min-height: 74px !important;
  height: 74px !important;
  font-size: 11px !important;
}
"""


INLINE_PANEL_SAFE_STYLE = """
.panel {
  gap: 12px !important;
}
.panel > div[style*="grid-template-rows:1fr 1fr"] {
  grid-template-rows: minmax(0, 1fr) minmax(0, 1fr) !important;
  gap: 10px !important;
  margin-bottom: 2px !important;
}
.panel > div[style*="grid-template-rows:1fr 1fr"] > article {
  padding: 12px !important;
}
.panel > div[style*="grid-template-rows:1fr 1fr"] > article > div:nth-child(2) {
  font-size: 28px !important;
  line-height: 1 !important;
}
.panel > div[style*="grid-template-rows:1fr 1fr"] > article > div:nth-child(3),
.panel > div[style*="grid-template-rows:1fr 1fr"] > article > div:nth-child(4),
.panel > div[style*="grid-template-rows:1fr 1fr"] > article p {
  font-size: 11px !important;
  line-height: 1.22 !important;
}
.panel > div[style*="display:flex"][style*="flex-wrap:wrap"] {
  gap: 6px !important;
  margin-top: 6px !important;
  padding-top: 2px !important;
}
.panel > div[style*="display:flex"][style*="flex-wrap:wrap"] > span {
  font-size: 10px !important;
  padding: 4px 8px !important;
}
"""


COVER_HEADER_SAFE_STYLE = """
.slide {
  grid-template-rows: minmax(114px, auto) 1fr auto !important;
}
.header {
  min-height: 114px !important;
}
.footer {
  min-height: 70px !important;
}
.header > .header-main {
  min-width: 0 !important;
}
"""


COVER_CHAIN_SAFE_STYLE = """
.main {
  padding-bottom: 10px !important;
}
.side-card {
  padding: 20px 20px !important;
  gap: 12px !important;
  justify-content: flex-start !important;
}
.side-top {
  gap: 12px !important;
  min-height: 0 !important;
}
.side-title {
  font-size: 20px !important;
  line-height: 1.18 !important;
}
.chain {
  gap: 10px !important;
}
.chain-item {
  grid-template-columns: 44px minmax(0, 1fr) !important;
  align-items: center !important;
  gap: 12px !important;
  min-height: 62px !important;
  padding: 10px 11px !important;
}
.num {
  align-self: center !important;
}
.chain-text {
  min-height: 44px !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
  gap: 3px !important;
}
.chain-text strong,
.chain-text span {
  display: block !important;
}
.chain-text strong {
  font-size: 15px !important;
  line-height: 1.24 !important;
}
.chain-text span {
  font-size: 13px !important;
  line-height: 1.38 !important;
}
.impact-box {
  margin-top: 10px !important;
  padding: 14px 16px !important;
  gap: 8px !important;
}
.impact-num {
  font-size: 24px !important;
  line-height: 1.02 !important;
}
.impact-text {
  font-size: 13px !important;
  line-height: 1.42 !important;
}
.tags {
  gap: 6px !important;
}
.tag {
  padding: 5px 9px !important;
  font-size: 11px !important;
  line-height: 1.1 !important;
}
.summary {
  padding: 15px 18px !important;
}
.summary-text {
  font-size: 17px !important;
  line-height: 1.45 !important;
}
"""


SIGNAL_DARK_COVER_SAFE_STYLE = """
.slide {
  grid-template-rows: 96px 1fr 64px !important;
  gap: 12px !important;
  padding: 20px 22px 20px !important;
}
.header {
  padding-bottom: 8px !important;
}
.title {
  font-size: 32px !important;
  line-height: 1.04 !important;
}
.subtitle {
  margin-top: 4px !important;
  font-size: 12px !important;
  line-height: 1.28 !important;
}
.corner-cluster {
  min-width: 166px !important;
  gap: 6px !important;
}
.page-tag {
  padding: 8px 12px !important;
}
.content {
  min-height: 0 !important;
}
.hero-panel {
  padding: 14px 16px 12px !important;
  display: grid !important;
  grid-template-rows: auto auto auto !important;
  align-content: start !important;
  row-gap: 10px !important;
}
.hero-top {
  grid-template-columns: minmax(0, 1fr) 270px !important;
  gap: 12px !important;
}
.hero-kicker {
  margin-bottom: 8px !important;
  font-size: 11px !important;
}
.thesis {
  max-width: 590px !important;
  font-size: 22px !important;
  line-height: 1.20 !important;
}
.hero-note {
  margin-top: 8px !important;
  max-width: 560px !important;
  font-size: 11px !important;
  line-height: 1.34 !important;
}
.support-cluster {
  padding: 12px 12px 10px !important;
  border-radius: 18px !important;
}
.support-title {
  margin-bottom: 8px !important;
  font-size: 11px !important;
}
.metric-grid {
  gap: 6px !important;
}
.metric-chip {
  min-height: 52px !important;
  padding: 8px !important;
  border-radius: 14px !important;
}
.metric-value {
  font-size: 20px !important;
}
.metric-label {
  margin-top: 4px !important;
  font-size: 9px !important;
  line-height: 1.22 !important;
}
.flow-zone {
  margin-top: 0 !important;
  gap: 8px !important;
  align-items: start !important;
}
.flow-card {
  min-height: 0 !important;
  padding: 10px 10px 8px !important;
  border-radius: 16px !important;
}
.flow-card::after {
  right: -8px !important;
  width: 16px !important;
}
.flow-card:not(:last-child)::before {
  right: -14px !important;
}
.icon-wrap {
  width: 30px !important;
  height: 30px !important;
  margin-bottom: 8px !important;
  border-radius: 12px !important;
}
.icon-wrap svg {
  width: 18px !important;
  height: 18px !important;
}
.flow-title {
  min-height: 30px !important;
  margin-bottom: 4px !important;
  font-size: 13px !important;
  line-height: 1.18 !important;
}
.flow-desc {
  min-height: auto !important;
  margin: 0 0 8px !important;
  font-size: 10px !important;
  line-height: 1.28 !important;
  display: -webkit-box !important;
  -webkit-box-orient: vertical !important;
  -webkit-line-clamp: 2 !important;
  overflow: hidden !important;
}
.flow-badge {
  padding: 5px 8px !important;
  gap: 4px !important;
  font-size: 9px !important;
}
.flow-badge .num {
  font-size: 14px !important;
}
.flow-card .flow-badge:nth-of-type(n+2) {
  display: none !important;
}
.bottom-band {
  margin-top: 8px !important;
  gap: 10px !important;
  padding: 8px 12px !important;
  border-radius: 16px !important;
}
.bottom-summary {
  font-size: 12px !important;
  line-height: 1.25 !important;
  display: -webkit-box !important;
  -webkit-box-orient: vertical !important;
  -webkit-line-clamp: 2 !important;
  overflow: hidden !important;
}
.capability-badges {
  max-width: 280px !important;
  gap: 5px !important;
}
.cap-badge {
  padding: 5px 8px !important;
  font-size: 9px !important;
}
.capability-badges .cap-badge:nth-child(n+3) {
  display: none !important;
}
.orbit-line {
  left: 62px !important;
  right: 62px !important;
  bottom: 64px !important;
  height: 86px !important;
}
.signal-dots {
  right: 30px !important;
  bottom: 98px !important;
}
.footer {
  min-height: 64px !important;
  font-size: 11px !important;
}
"""


SIGNAL_DARK_TOC_SAFE_STYLE = """
.slide {
  grid-template-rows: 100px 1fr 68px !important;
  gap: 14px !important;
  padding: 22px 24px 22px !important;
}
.header {
  padding-bottom: 10px !important;
}
.title {
  font-size: 34px !important;
  line-height: 1.06 !important;
}
.subtitle {
  margin-top: 6px !important;
  font-size: 13px !important;
  line-height: 1.34 !important;
}
.content {
  min-height: 0 !important;
}
.toc-stage {
  gap: 12px !important;
  padding: 2px 0 0 !important;
}
.intro-band {
  min-height: 72px !important;
  gap: 14px !important;
}
.intro-copy {
  padding: 14px 16px !important;
}
.intro-title {
  font-size: 14px !important;
}
.intro-text {
  margin-top: 6px !important;
  font-size: 12px !important;
  line-height: 1.42 !important;
}
.intro-chips {
  gap: 8px !important;
}
.flow-chip {
  padding: 8px 12px !important;
  font-size: 11px !important;
}
.toc-cards {
  gap: 14px !important;
}
.toc-cards::after {
  bottom: 22px !important;
}
.toc-card {
  padding: 18px 16px 16px !important;
}
.card-index {
  font-size: 34px !important;
}
.card-icon {
  width: 38px !important;
  height: 38px !important;
}
.card-part {
  margin-top: 12px !important;
  font-size: 11px !important;
}
.card-title {
  min-height: 50px !important;
  margin-top: 8px !important;
  font-size: 20px !important;
  line-height: 1.2 !important;
}
.card-desc {
  min-height: 42px !important;
  margin-top: 8px !important;
  font-size: 12px !important;
  line-height: 1.42 !important;
}
.keyword-group {
  margin-top: 12px !important;
  gap: 6px !important;
}
.keyword {
  padding: 6px 8px !important;
  font-size: 10px !important;
}
.keyword-group .keyword:nth-child(n+3) {
  display: none !important;
}
.card-foot {
  margin-top: 10px !important;
  padding-top: 8px !important;
  display: none !important;
}
.foot-label {
  font-size: 11px !important;
}
.foot-arrow {
  width: 28px !important;
  height: 28px !important;
}
.support-strip {
  min-height: 64px !important;
  gap: 14px !important;
}
.summary-bar {
  gap: 10px !important;
  padding: 12px 14px !important;
}
.summary-copy strong {
  font-size: 13px !important;
}
.summary-copy span {
  font-size: 11px !important;
  line-height: 1.35 !important;
}
.mini-metrics {
  padding: 12px 14px !important;
  gap: 10px !important;
}
.metric-label,
.metric-note {
  font-size: 10px !important;
  line-height: 1.28 !important;
}
.metric-value {
  font-size: 22px !important;
}
.footer {
  min-height: 68px !important;
}
"""


SIGNAL_DARK_ENDING_SAFE_STYLE = """
.slide {
  grid-template-rows: 100px 1fr 70px !important;
  gap: 14px !important;
  padding: 22px 24px 22px !important;
}
.header {
  padding-bottom: 10px !important;
}
.title {
  font-size: 33px !important;
  line-height: 1.06 !important;
}
.subtitle {
  margin-top: 6px !important;
  font-size: 13px !important;
  line-height: 1.34 !important;
}
.content {
  gap: 12px !important;
  min-height: 0 !important;
}
.logic-board {
  grid-template-columns: 1fr 0.86fr 1.02fr !important;
  gap: 12px !important;
}
.panel {
  padding: 16px !important;
}
.section-label {
  margin-bottom: 12px !important;
  padding: 6px 10px !important;
  font-size: 10px !important;
}
.pain-list {
  gap: 10px !important;
}
.pain-card,
.value-item {
  grid-template-columns: 38px 1fr !important;
  gap: 10px !important;
  padding: 11px 11px 10px !important;
}
.pain-icon,
.value-icon {
  width: 38px !important;
  height: 38px !important;
}
.card-title {
  margin: 1px 0 4px !important;
  font-size: 16px !important;
  line-height: 1.1 !important;
}
.card-desc,
.value-item span {
  font-size: 11px !important;
  line-height: 1.32 !important;
}
.value-item strong {
  margin: 2px 0 4px !important;
  font-size: 15px !important;
  line-height: 1.16 !important;
}
.core-badge {
  padding: 6px 10px !important;
  font-size: 10px !important;
}
.core-visual {
  margin-top: 14px !important;
  height: 130px !important;
}
.ring-1 {
  width: 140px !important;
  height: 140px !important;
}
.ring-2 {
  width: 104px !important;
  height: 104px !important;
}
.ring-3 {
  width: 68px !important;
  height: 68px !important;
}
.node-a {
  top: 18px !important;
}
.node-b {
  right: 28px !important;
}
.node-c {
  bottom: 18px !important;
}
.node-d {
  left: 28px !important;
}
.core-center {
  width: 100px !important;
  height: 100px !important;
  border-radius: 24px !important;
}
.core-center svg {
  width: 28px !important;
  height: 28px !important;
  margin-bottom: 8px !important;
}
.core-name {
  font-size: 14px !important;
}
.core-sub {
  margin-top: 2px !important;
  font-size: 10px !important;
}
.core-copy {
  margin-top: 8px !important;
}
.core-headline {
  font-size: 18px !important;
  line-height: 1.2 !important;
}
.core-desc {
  margin-top: 8px !important;
  font-size: 11px !important;
  line-height: 1.34 !important;
}
.chip-grid {
  margin-top: 12px !important;
  gap: 8px !important;
}
.impact-chip {
  padding: 6px 10px !important;
  font-size: 10px !important;
}
.chip-grid .impact-chip:nth-child(n+3) {
  display: none !important;
}
.value-panel {
  grid-template-rows: auto 1fr auto !important;
  gap: 10px !important;
}
.value-list {
  gap: 9px !important;
}
.priority-box {
  padding: 12px 12px 10px !important;
}
.priority-title {
  margin-bottom: 8px !important;
  font-size: 13px !important;
}
.priority-chips {
  gap: 6px !important;
  margin-bottom: 8px !important;
}
.mini-chip {
  padding: 6px 8px !important;
  font-size: 10px !important;
}
.priority-chips .mini-chip:nth-child(n+3) {
  display: none !important;
}
.priority-note {
  font-size: 10px !important;
  line-height: 1.3 !important;
}
.summary-strip {
  min-height: 64px !important;
  grid-template-columns: 156px 1fr auto !important;
  gap: 12px !important;
  padding: 12px 14px !important;
}
.summary-kicker {
  padding: 10px 12px !important;
  font-size: 11px !important;
}
.summary-text {
  font-size: 20px !important;
  line-height: 1.18 !important;
}
.summary-tags {
  gap: 6px !important;
}
.summary-tag {
  padding: 6px 8px !important;
  font-size: 10px !important;
}
.summary-tags .summary-tag:nth-child(n+3) {
  display: none !important;
}
.footer {
  min-height: 70px !important;
}
"""




def _inspect_html_layout(page) -> dict:
    return page.evaluate(
        """
        () => {
          const slide = document.querySelector('.slide');
          const header = document.querySelector('.header');
          const main = document.querySelector('.main');
          const footer = document.querySelector('.footer');

          const overflowSelectors = [
            '.card', '.stage', '.step', '.summary-card', '.footer-card',
            '.launch-box', '.summary', '.flow', '.node', '.metric', '.metric-box',
            '.scene-item', '.policy-box', '.timeline-summary', '.card-sub', '.metric-note'
          ];

          const getRect = (el) => {
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {
              top: Math.round(r.top),
              bottom: Math.round(r.bottom),
              left: Math.round(r.left),
              right: Math.round(r.right),
              width: Math.round(r.width),
              height: Math.round(r.height),
            };
          };

          const normalizeText = (value) => (value || '').replace(/\\s+/g, ' ').trim();

          const collectOverflow = () => {
            const items = [];
            for (const selector of overflowSelectors) {
              document.querySelectorAll(selector).forEach((el, index) => {
                const sh = el.scrollHeight;
                const ch = el.clientHeight;
                const sw = el.scrollWidth;
                const cw = el.clientWidth;
                if (sh > ch + 2 || sw > cw + 2) {
                  items.push({
                    selector,
                    index,
                    scrollHeight: sh,
                    clientHeight: ch,
                    scrollWidth: sw,
                    clientWidth: cw,
                    text: normalizeText(el.innerText || '').slice(0, 80),
                  });
                }
              });
            }
            return items;
          };

          const isDecorativeElement = (el) => {
            if (!(el instanceof HTMLElement)) return true;
            const text = normalizeText(el.innerText || '');
            const classes = Array.from(el.classList || []).join(' ').toLowerCase();
            const ariaHidden = (el.getAttribute('aria-hidden') || '').toLowerCase() === 'true';
            const decorativeTokens = [
              'ambient', 'orb', 'glow', 'ring', 'signal-node', 'corner-dot',
              'corner-orbit', 'orbit-line', 'sr-only'
            ];
            const meaningfulHiddenTokens = ['icon', 'arrow', 'badge', 'page-tag'];
            if (classes && decorativeTokens.some((token) => classes.includes(token))) {
              return true;
            }
            if (ariaHidden && !text && !meaningfulHiddenTokens.some((token) => classes.includes(token))) {
              return true;
            }
            const tag = el.tagName.toLowerCase();
            if (!text && ['svg', 'path', 'circle'].includes(tag)) {
              return true;
            }
            return false;
          };

          const collectChipCollisions = () => {
            const items = [];
            const parents = Array.from(document.querySelectorAll('.panel, .card, article')).filter(
              (el) => el instanceof HTMLElement
            );
            for (const parent of parents) {
              const children = Array.from(parent.children).filter((el) => el instanceof HTMLElement);
              children.forEach((child, index) => {
                const inlineStyle = (child.getAttribute('style') || '').toLowerCase();
                const isChipRow = (
                  child.matches('.tags, .mini-tags, .tag-row, .summary-tags, .footer-tags')
                  || (inlineStyle.includes('display:flex') && inlineStyle.includes('flex-wrap:wrap'))
                );
                if (!isChipRow || index === 0) return;
                const prev = children[index - 1];
                const prevRect = prev.getBoundingClientRect();
                const rowRect = child.getBoundingClientRect();
                if (rowRect.top < prevRect.bottom + 6) {
                  items.push({
                    parentTag: parent.tagName.toLowerCase(),
                    index,
                    delta: Math.round(prevRect.bottom + 6 - rowRect.top),
                    rowText: normalizeText(child.innerText || '').slice(0, 60),
                  });
                }
              });
            }
            return items;
          };

          const identifyNode = (el) => {
            if (!el) return 'unknown';
            const classes = Array.from(el.classList || []).filter(Boolean);
            if (classes.length) {
              return `.${classes.slice(0, 2).join('.')}`;
            }
            return el.tagName.toLowerCase();
          };

          const collectClippedDescendants = () => {
            const items = [];
            if (!slide) return items;
            const slideRect = slide.getBoundingClientRect();
            const seen = new Set();
            const nodes = Array.from(document.querySelectorAll('.slide *')).filter(
              (el) => el instanceof HTMLElement
            );

            for (const el of nodes) {
              if (isDecorativeElement(el)) continue;
              const rect = el.getBoundingClientRect();
              if (rect.width <= 2 || rect.height <= 2) continue;
              const bottomDelta = Math.max(0, Math.round((rect.bottom - slideRect.bottom) * 10) / 10);
              const rightDelta = Math.max(0, Math.round((rect.right - slideRect.right) * 10) / 10);
              const topDelta = Math.max(0, Math.round((slideRect.top - rect.top) * 10) / 10);
              const leftDelta = Math.max(0, Math.round((slideRect.left - rect.left) * 10) / 10);
              if (bottomDelta <= 1 && rightDelta <= 1 && topDelta <= 1 && leftDelta <= 1) {
                continue;
              }
              const signature = [
                el.tagName.toLowerCase(),
                identifyNode(el),
                Math.round(rect.top),
                Math.round(rect.left),
                Math.round(rect.bottom),
                Math.round(rect.right),
              ].join('|');
              if (seen.has(signature)) continue;
              seen.add(signature);
              items.push({
                selector: identifyNode(el),
                tag: el.tagName.toLowerCase(),
                bottom: Math.round(rect.bottom),
                right: Math.round(rect.right),
                bottomDelta,
                rightDelta,
                topDelta,
                leftDelta,
                text: normalizeText(el.innerText || '').slice(0, 80),
              });
            }

            items.sort((left, right) => {
              const leftDelta = Math.max(left.bottomDelta, left.rightDelta, left.topDelta, left.leftDelta);
              const rightDelta = Math.max(right.bottomDelta, right.rightDelta, right.topDelta, right.leftDelta);
              return rightDelta - leftDelta;
            });
            return items.slice(0, 16);
          };

          const collectFooterIntrusions = () => {
            const items = [];
            if (!main || !footer) return items;
            const footerRect = footer.getBoundingClientRect();
            const candidates = Array.from(
              main.querySelectorAll(
                '.side-card, .impact-box, .tags, .tag, .card, article, .panel, .summary-card, .footer-card'
              )
            ).filter((el) => el instanceof HTMLElement);

            for (const candidate of candidates) {
              const rect = candidate.getBoundingClientRect();
              const delta = Math.round(rect.bottom + 8 - footerRect.top);
              if (delta > 0) {
                items.push({
                  selector: identifyNode(candidate),
                  delta,
                  text: normalizeText(candidate.innerText || '').slice(0, 80),
                });
              }
            }

            return items;
          };

          const collectSignalDarkCollisions = () => {
            const items = [];
            const bottomBand = document.querySelector('.bottom-band');
            const footerEl = document.querySelector('.footer');
            const flowCards = Array.from(document.querySelectorAll('.flow-zone .flow-card')).filter(
              (el) => el instanceof HTMLElement
            );

            if (bottomBand && flowCards.length) {
              const bandRect = bottomBand.getBoundingClientRect();
              flowCards.forEach((card, index) => {
                const cardRect = card.getBoundingClientRect();
                const delta = Math.round((cardRect.bottom + 8 - bandRect.top) * 10) / 10;
                if (delta > 0) {
                  items.push({
                    kind: 'flow-to-band',
                    index,
                    delta,
                    text: normalizeText(card.innerText || '').slice(0, 80),
                  });
                }
              });
            }

            if (bottomBand && footerEl) {
              const bandRect = bottomBand.getBoundingClientRect();
              const footerRect = footerEl.getBoundingClientRect();
              const delta = Math.round((bandRect.bottom + 6 - footerRect.top) * 10) / 10;
              if (delta > 0) {
                items.push({
                  kind: 'band-to-footer',
                  delta,
                  text: normalizeText(bottomBand.innerText || '').slice(0, 80),
                });
              }
            }

            return items;
          };

          const slideRect = getRect(slide);
          const headerRect = getRect(header);
          const mainRect = getRect(main);
          const footerRect = getRect(footer);
          const overlap = Boolean(mainRect && footerRect && mainRect.bottom > footerRect.top);
          const slideOverflow = slide ? slide.scrollHeight > slide.clientHeight + 2 : false;

          const boundarySelectors = [
            '.title', '.subtitle', '.summary-card', '.footer-card',
            '.card-title', '.card-sub', '.footer-text', '.timeline-summary', '.policy-title'
          ];
          const boundaryIssues = [];
          if (slideRect) {
            for (const selector of boundarySelectors) {
              document.querySelectorAll(selector).forEach((el, index) => {
                const rect = getRect(el);
                if (!rect) return;
                if (rect.right > slideRect.right + 1 || rect.bottom > slideRect.bottom + 1) {
                  boundaryIssues.push({ selector, index, rect });
                }
              });
            }
          }

          const summaryHeavy = Boolean(
            footer
            && main
            && document.querySelector('.decision-steps')
            && document.querySelector('.metric-card')
            && window.getComputedStyle(main).gridTemplateColumns.split(' ').length >= 3
          );

          const timelineHeavy = Boolean(
            (document.querySelector('.timeline-wrap') && document.querySelectorAll('.timeline-wrap .node').length >= 4)
            || (
              document.querySelector('.timeline')
              && (
                document.querySelectorAll('.timeline .step').length >= 4
                || document.querySelectorAll('.timeline .node').length >= 4
              )
              && document.querySelector('.right-col, .right-grid, .metrics, .metrics-grid, .bottom')
            )
          );

          const denseCardHeavy = Boolean(
            document.querySelectorAll('.card, .metric-card, .stats-card, .evidence-card, .talk-card, .scene-card').length >= 2
            && (
              document.querySelector('.logic-row')
              || document.querySelector('.stat-grid')
              || document.querySelector('.node-grid')
              || document.querySelector('.metrics-grid')
              || document.querySelector('.metrics')
              || document.querySelector('.scene-top')
              || document.querySelector('.policy-box')
              || document.querySelector('.bottom')
            )
          );

          const inlineDensePanel = Array.from(document.querySelectorAll('.panel')).some((panel) => {
            const children = Array.from(panel.children).filter((el) => el instanceof HTMLElement);
            const hasTwoRowGrid = children.some((child) => {
              const style = (child.getAttribute('style') || '').toLowerCase();
              return style.includes('display:grid') && style.includes('grid-template-rows:1fr 1fr');
            });
            const hasChipRow = children.some((child) => {
              const style = (child.getAttribute('style') || '').toLowerCase();
              return style.includes('display:flex') && style.includes('flex-wrap:wrap');
            });
            return hasTwoRowGrid && hasChipRow;
          });

          const chipCollisions = collectChipCollisions();
          const clippedDescendants = collectClippedDescendants();
          const footerIntrusions = collectFooterIntrusions();
          const signalDarkCollisions = collectSignalDarkCollisions();

          const tocSparse = Boolean(
            document.querySelector('.steps')
            && document.querySelector('.flow-card')
            && document.querySelector('.left-card')
            && !document.querySelector('.flow-fill')
          );

          const conclusionHeavy = Boolean(
            document.querySelector('.decision-card')
            && document.querySelector('.split-result')
            && document.querySelector('.summary-card')
          );

          const stepCardHeavy = Boolean(
            document.querySelector('.steps')
            && document.querySelectorAll('.steps .step').length >= 3
          );

          const dualPanelCover = Boolean(
            document.querySelector('.hero-left')
            && document.querySelector('.hero-right')
            && document.querySelector('.hero-bottom')
            && document.querySelector('.loop-box')
            && document.querySelectorAll('.logic-card').length >= 3
            && document.querySelectorAll('.metric-card').length >= 3
          );

          const signalDarkCover = Boolean(
            document.querySelector('.hero-panel')
            && document.querySelector('.flow-zone')
            && document.querySelectorAll('.flow-card').length >= 4
          );

          const signalDarkToc = Boolean(
            document.querySelector('.toc-stage')
            && document.querySelectorAll('.toc-card').length >= 3
            && document.querySelector('.support-strip')
          );

          const signalDarkEnding = Boolean(
            document.querySelector('.logic-board')
            && document.querySelector('.core-panel')
            && document.querySelector('.value-panel')
          );

          return {
            slide: slide ? {
              scrollHeight: slide.scrollHeight,
              clientHeight: slide.clientHeight,
              scrollWidth: slide.scrollWidth,
              clientWidth: slide.clientWidth,
              rect: slideRect,
            } : null,
            header: header ? { rect: headerRect } : null,
            main: main ? { rect: mainRect } : null,
            footer: footer ? { rect: footerRect } : null,
            overlap,
            slideOverflow,
            overflowItems: collectOverflow(),
            clippedDescendants,
            chipCollisions,
            footerIntrusions,
            signalDarkCollisions,
            boundaryIssues,
            summaryHeavy,
            timelineHeavy,
            denseCardHeavy: denseCardHeavy || inlineDensePanel,
            tocSparse,
            conclusionHeavy,
            stepCardHeavy,
            dualPanelCover,
            signalDarkCover,
            signalDarkToc,
            signalDarkEnding,
          };
        }
        """
    )




def _summarize_layout_issues(report: dict) -> list[str]:
    issues = []
    slide = report.get("slide") or {}
    header = report.get("header") or {}
    slide_rect = slide.get("rect") or {}

    if report.get("slideOverflow"):
        issues.append(
            f"slide 高度超限：scrollHeight={slide.get('scrollHeight')} > clientHeight={slide.get('clientHeight')}"
        )

    if report.get("overlap"):
        main_rect = (report.get("main") or {}).get("rect") or {}
        footer_rect = (report.get("footer") or {}).get("rect") or {}
        issues.append(
            f"main/footer 重叠：main.bottom={main_rect.get('bottom')} > footer.top={footer_rect.get('top')}"
        )

    header_rect = header.get("rect") or {}
    if header_rect.get("height", 0) > 118 and header_rect.get("top", 0) <= slide_rect.get("top", 0) + 12:
        issues.append(f"header 过高：height={header_rect.get('height')}px")

    for item in (report.get("overflowItems") or [])[:5]:
        if item.get("scrollHeight", 0) > item.get("clientHeight", 0) + 2:
            issues.append(
                f"{item['selector']}#{item['index']} 垂直溢出：{item['scrollHeight']}>{item['clientHeight']} 文本={item['text']}"
            )
        elif item.get("scrollWidth", 0) > item.get("clientWidth", 0) + 2:
            issues.append(
                f"{item['selector']}#{item['index']} 水平溢出：{item['scrollWidth']}>{item['clientWidth']} 文本={item['text']}"
            )

    for item in (report.get("boundaryIssues") or [])[:3]:
        rect = item.get("rect") or {}
        issues.append(
            f"{item['selector']}#{item['index']} 超出 slide 边界：right={rect.get('right')}, bottom={rect.get('bottom')}"
        )

    for item in (report.get("clippedDescendants") or [])[:5]:
        deltas = []
        if item.get("bottomDelta", 0) > 1:
            deltas.append(f"bottom+{item['bottomDelta']}")
        if item.get("rightDelta", 0) > 1:
            deltas.append(f"right+{item['rightDelta']}")
        if item.get("topDelta", 0) > 1:
            deltas.append(f"top+{item['topDelta']}")
        if item.get("leftDelta", 0) > 1:
            deltas.append(f"left+{item['leftDelta']}")
        delta_text = ",".join(deltas) if deltas else "beyond-safe-area"
        issues.append(f"{item['selector']} 被 slide 裁切：{delta_text} 文本={item['text']}")

    for item in (report.get("chipCollisions") or [])[:4]:
        issues.append(
            f"{item['parentTag']} 内部 tag/chip 行与上方内容过近，delta={item['delta']} 文本={item['rowText']}"
        )

    for item in (report.get("footerIntrusions") or [])[:4]:
        issues.append(
            f"{item['selector']} 侵入 footer 安全区，delta={item['delta']} 文本={item['text']}"
        )

    for item in (report.get("signalDarkCollisions") or [])[:6]:
        if item.get("kind") == "flow-to-band":
            issues.append(
                f"signal-dark cover flow-card#{item['index']} overlaps bottom-band, delta={item['delta']} text={item['text']}"
            )
        else:
            issues.append(
                f"signal-dark cover bottom-band intrudes footer safe area, delta={item['delta']} text={item['text']}"
            )

    return issues


def _should_regenerate(report: dict) -> bool:
    overflow_items = report.get("overflowItems") or []
    clipped_items = report.get("clippedDescendants") or []
    severe_overflow_count = sum(
        1
        for item in overflow_items
        if (item.get("scrollHeight", 0) - item.get("clientHeight", 0) > 14)
        or (item.get("scrollWidth", 0) - item.get("clientWidth", 0) > 14)
    )
    severe_clipped_count = sum(
        1
        for item in clipped_items
        if max(
            item.get("bottomDelta", 0),
            item.get("rightDelta", 0),
            item.get("topDelta", 0),
            item.get("leftDelta", 0),
        ) > 10
    )
    total_overflow_count = len(overflow_items)
    total_clipped_count = len(clipped_items)
    slide_rect = ((report.get("slide") or {}).get("rect") or {})
    header_rect = ((report.get("header") or {}).get("rect") or {})
    header_height = ((report.get("header") or {}).get("rect") or {}).get("height", 0)
    header_tight_and_tall = header_height > 118 and header_rect.get("top", 0) <= slide_rect.get("top", 0) + 12
    slide_delta = (report.get("slide") or {}).get("scrollHeight", 0) - (report.get("slide") or {}).get("clientHeight", 0)
    signal_dark_collisions = report.get("signalDarkCollisions") or []
    severe_signal_dark_collision = any(item.get("delta", 0) > 6 for item in signal_dark_collisions)

    high_risk_dense_page = (
        report.get("timelineHeavy")
        or report.get("denseCardHeavy")
        or report.get("dualPanelCover")
        or report.get("signalDarkCover")
        or report.get("signalDarkToc")
        or report.get("signalDarkEnding")
    )

    return bool(
        report.get("overlap")
        or severe_overflow_count >= 1
        or severe_clipped_count >= 1
        or total_overflow_count >= 3
        or total_clipped_count >= 3
        or header_tight_and_tall
        or slide_delta > 12
        or severe_signal_dark_collision
        or len(report.get("boundaryIssues") or []) >= 2
        or (high_risk_dense_page and (total_overflow_count >= 1 or total_clipped_count >= 1))
    )




def _apply_compact_mode(page) -> None:
    page.add_style_tag(content=COMPACT_STYLE)


def _apply_summary_safe_mode(page) -> None:
    page.add_style_tag(content=SUMMARY_SAFE_STYLE)


def _apply_timeline_safe_mode(page) -> None:
    page.add_style_tag(content=TIMELINE_SAFE_STYLE)


def _apply_dense_card_safe_mode(page) -> None:
    page.add_style_tag(content=DENSE_CARD_SAFE_STYLE)


def _apply_dual_panel_cover_safe_mode(page) -> None:
    page.add_style_tag(content=DUAL_PANEL_COVER_SAFE_STYLE)


def _apply_inline_panel_safe_mode(page) -> None:
    page.add_style_tag(content=INLINE_PANEL_SAFE_STYLE)


def _apply_cover_header_safe_mode(page) -> None:
    page.add_style_tag(content=COVER_HEADER_SAFE_STYLE)


def _apply_cover_chain_safe_mode(page) -> None:
    page.add_style_tag(content=COVER_CHAIN_SAFE_STYLE)


def _apply_signal_dark_cover_safe_mode(page) -> None:
    page.add_style_tag(content=SIGNAL_DARK_COVER_SAFE_STYLE)


def _apply_signal_dark_toc_safe_mode(page) -> None:
    page.add_style_tag(content=SIGNAL_DARK_TOC_SAFE_STYLE)


def _apply_signal_dark_ending_safe_mode(page) -> None:
    page.add_style_tag(content=SIGNAL_DARK_ENDING_SAFE_STYLE)


def _apply_toc_safe_mode(page) -> None:
    page.add_style_tag(content=TOC_SAFE_STYLE)


def _apply_conclusion_safe_mode(page) -> None:
    page.add_style_tag(content=CONCLUSION_SAFE_STYLE)


def _apply_step_card_safe_mode(page) -> None:
    page.add_style_tag(content=STEP_CARD_SAFE_STYLE)


def _persist_style(html_path: Path, original_html: str, style_id: str, style_content: str) -> str:
    style_tag = f"<style id=\"{style_id}\">\n{style_content}\n</style>"
    if f'id="{style_id}"' in original_html:
        updated_html = re.sub(
            rf'<style id="{re.escape(style_id)}">.*?</style>',
            style_tag,
            original_html,
            count=1,
            flags=re.DOTALL,
        )
    elif "</head>" in original_html:
        updated_html = original_html.replace("</head>", f"{style_tag}\n</head>", 1)
    else:
        updated_html = original_html + "\n" + style_tag
    html_path.write_text(updated_html, encoding="utf-8")
    return updated_html


def _persist_compact_html(html_path: Path, original_html: str) -> str:
    return _persist_style(html_path, original_html, "claude-compact-style", COMPACT_STYLE)


def _persist_summary_safe_html(html_path: Path, original_html: str) -> str:
    return _persist_style(html_path, original_html, "claude-summary-safe-style", SUMMARY_SAFE_STYLE)


def _persist_timeline_safe_html(html_path: Path, original_html: str) -> str:
    return _persist_style(html_path, original_html, "claude-timeline-safe-style", TIMELINE_SAFE_STYLE)


def _persist_dense_card_safe_html(html_path: Path, original_html: str) -> str:
    return _persist_style(html_path, original_html, "claude-dense-card-safe-style", DENSE_CARD_SAFE_STYLE)


def _persist_dual_panel_cover_safe_html(html_path: Path, original_html: str) -> str:
    return _persist_style(
        html_path,
        original_html,
        "claude-dual-panel-cover-safe-style",
        DUAL_PANEL_COVER_SAFE_STYLE,
    )


def _persist_inline_panel_safe_html(html_path: Path, original_html: str) -> str:
    return _persist_style(html_path, original_html, "claude-inline-panel-safe-style", INLINE_PANEL_SAFE_STYLE)


def _persist_cover_header_safe_html(html_path: Path, original_html: str) -> str:
    return _persist_style(html_path, original_html, "claude-cover-header-safe-style", COVER_HEADER_SAFE_STYLE)


def _persist_cover_chain_safe_html(html_path: Path, original_html: str) -> str:
    return _persist_style(html_path, original_html, "claude-cover-chain-safe-style", COVER_CHAIN_SAFE_STYLE)


def _persist_signal_dark_cover_safe_html(html_path: Path, original_html: str) -> str:
    return _persist_style(
        html_path,
        original_html,
        "claude-signal-dark-cover-safe-style",
        SIGNAL_DARK_COVER_SAFE_STYLE,
    )


def _persist_signal_dark_toc_safe_html(html_path: Path, original_html: str) -> str:
    return _persist_style(
        html_path,
        original_html,
        "claude-signal-dark-toc-safe-style",
        SIGNAL_DARK_TOC_SAFE_STYLE,
    )


def _persist_signal_dark_ending_safe_html(html_path: Path, original_html: str) -> str:
    return _persist_style(
        html_path,
        original_html,
        "claude-signal-dark-ending-safe-style",
        SIGNAL_DARK_ENDING_SAFE_STYLE,
    )


def _persist_toc_safe_html(html_path: Path, original_html: str) -> str:
    return _persist_style(html_path, original_html, "claude-toc-safe-style", TOC_SAFE_STYLE)


def _persist_conclusion_safe_html(html_path: Path, original_html: str) -> str:
    return _persist_style(html_path, original_html, "claude-conclusion-safe-style", CONCLUSION_SAFE_STYLE)


def _persist_step_card_safe_html(html_path: Path, original_html: str) -> str:
    return _persist_style(html_path, original_html, "claude-step-card-safe-style", STEP_CARD_SAFE_STYLE)


def _normalize_cover_metric_copy(text: str) -> str:
    cleaned = re.sub(r"^\s*\d+\s*", "", text).strip()
    if not cleaned:
        return text.strip()
    if cleaned.startswith("重"):
        return "多" + cleaned
    return cleaned


def _persist_cover_sequence_fix_html(html_path: Path, original_html: str) -> tuple[str, bool]:
    changed = False

    def replace_metric(match: re.Match[str]) -> str:
        nonlocal changed
        text = match.group(2)
        if not re.match(r"^\s*\d+\s*", text):
            return match.group(0)
        normalized = _normalize_cover_metric_copy(text)
        if normalized != text.strip():
            changed = True
        return f"{match.group(1)}{normalized}{match.group(3)}"

    updated_html = re.sub(
        r'(<(?:div|span|p)[^>]*class="[^"]*impact-num[^"]*"[^>]*>)([^<]+)(</(?:div|span|p)>)',
        replace_metric,
        original_html,
    )
    if changed:
        html_path.write_text(updated_html, encoding="utf-8")
    return updated_html, changed




def render_html_with_validation(html_path: Path) -> tuple[bytes, dict]:
    html_content = html_path.read_text(encoding="utf-8")
    persisted_compact = False
    persisted_summary_safe = False
    persisted_timeline_safe = False
    persisted_dense_card_safe = False
    persisted_dual_panel_cover_safe = False
    persisted_inline_panel_safe = False
    persisted_cover_header_safe = False
    persisted_cover_chain_safe = False
    persisted_signal_dark_cover_safe = False
    persisted_signal_dark_toc_safe = False
    persisted_signal_dark_ending_safe = False
    persisted_cover_sequence_fix = False
    persisted_toc_safe = False
    persisted_conclusion_safe = False
    persisted_step_card_safe = False
    summary_safe_applied = False
    timeline_safe_applied = False
    dense_card_safe_applied = False
    dual_panel_cover_safe_applied = False
    inline_panel_safe_applied = False
    cover_header_safe_applied = False
    cover_chain_safe_applied = False
    signal_dark_cover_safe_applied = False
    signal_dark_toc_safe_applied = False
    signal_dark_ending_safe_applied = False
    toc_safe_applied = False
    conclusion_safe_applied = False
    step_card_safe_applied = False
    with sync_playwright() as p:
        browser = launch_global_chromium(p)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.set_content(html_content, wait_until="networkidle")

        cover_header_structure = page.evaluate(
            """
            () => {
              const slide = document.querySelector('.slide');
              const header = document.querySelector('.header');
              const main = document.querySelector('.header-main');
              const title = document.querySelector('.title');
              const subtitle = document.querySelector('.subtitle');
              const eyebrow = document.querySelector('.eyebrow');
              const cornerCluster = document.querySelector('.corner-cluster');
              if (!slide || !header || !main || !title || !subtitle || !eyebrow || !cornerCluster) {
                return false;
              }
              const slideRect = slide.getBoundingClientRect();
              const headerRect = header.getBoundingClientRect();
              const mainRect = main.getBoundingClientRect();
              const titleRect = title.getBoundingClientRect();
              const topGap = mainRect.top - slideRect.top;
              const titleTopGap = titleRect.top - slideRect.top;
              return topGap < 8 && titleTopGap < 56 && headerRect.height <= mainRect.height + 4;
            }
            """
        )
        if cover_header_structure:
            _apply_cover_header_safe_mode(page)
            cover_header_safe_applied = True
            persisted_cover_header_safe = True
            html_content = _persist_cover_header_safe_html(html_path, html_content)

        cover_chain_structure = page.evaluate(
            """
            () => Boolean(
              document.querySelector('.chain-item .num')
              && document.querySelector('.chain-item .chain-text')
              && document.querySelector('.impact-num')
            )
            """
        )
        if cover_chain_structure:
            _apply_cover_chain_safe_mode(page)
            cover_chain_safe_applied = True
            persisted_cover_chain_safe = True
            page.evaluate(
                """
                () => {
                  const impact = document.querySelector('.impact-num');
                  if (!impact) return;
                  const raw = (impact.textContent || '').trim();
                  if (!/^\\d+\\s*/.test(raw)) return;
                  let normalized = raw.replace(/^\\d+\\s*/, '').trim();
                  if (normalized.startsWith('\u91cd')) {
                    normalized = `\u591a${normalized}`;
                  }
                  impact.textContent = normalized;
                }
                """
            )
            html_content = _persist_cover_chain_safe_html(html_path, html_content)
            html_content, persisted_cover_sequence_fix = _persist_cover_sequence_fix_html(html_path, html_content)

        inline_panel_structure = page.evaluate(
            """
            () => Array.from(document.querySelectorAll('.panel')).some((panel) => {
              const children = Array.from(panel.children).filter((el) => el instanceof HTMLElement);
              const hasTwoRowGrid = children.some((child) => {
                const style = (child.getAttribute('style') || '').toLowerCase();
                return style.includes('display:grid') && style.includes('grid-template-rows:1fr 1fr');
              });
              const hasChipRow = children.some((child) => {
                const style = (child.getAttribute('style') || '').toLowerCase();
                return style.includes('display:flex') && style.includes('flex-wrap:wrap');
              });
              return hasTwoRowGrid && hasChipRow;
            })
            """
        )
        if inline_panel_structure:
            _apply_inline_panel_safe_mode(page)
            inline_panel_safe_applied = True
            persisted_inline_panel_safe = True
            html_content = _persist_inline_panel_safe_html(html_path, html_content)

        initial_report = _inspect_html_layout(page)
        initial_issues = _summarize_layout_issues(initial_report)

        final_report = initial_report
        final_issues = initial_issues

        if final_report.get("signalDarkCover"):
            _apply_signal_dark_cover_safe_mode(page)
            signal_dark_cover_safe_applied = True
            persisted_signal_dark_cover_safe = True
            final_report = _inspect_html_layout(page)
            final_issues = _summarize_layout_issues(final_report)
            html_content = _persist_signal_dark_cover_safe_html(html_path, html_content)

        if final_report.get("signalDarkToc"):
            _apply_signal_dark_toc_safe_mode(page)
            signal_dark_toc_safe_applied = True
            persisted_signal_dark_toc_safe = True
            final_report = _inspect_html_layout(page)
            final_issues = _summarize_layout_issues(final_report)
            html_content = _persist_signal_dark_toc_safe_html(html_path, html_content)

        if final_report.get("signalDarkEnding"):
            _apply_signal_dark_ending_safe_mode(page)
            signal_dark_ending_safe_applied = True
            persisted_signal_dark_ending_safe = True
            final_report = _inspect_html_layout(page)
            final_issues = _summarize_layout_issues(final_report)
            html_content = _persist_signal_dark_ending_safe_html(html_path, html_content)

        if final_report.get("tocSparse"):
            _apply_toc_safe_mode(page)
            toc_safe_applied = True
            persisted_toc_safe = True
            final_report = _inspect_html_layout(page)
            final_issues = _summarize_layout_issues(final_report)
            html_content = _persist_toc_safe_html(html_path, html_content)

        if final_report.get("timelineHeavy") and (final_report.get("overlap") or len(final_issues) >= 3):
            _apply_timeline_safe_mode(page)
            timeline_safe_applied = True
            persisted_timeline_safe = True
            final_report = _inspect_html_layout(page)
            final_issues = _summarize_layout_issues(final_report)
            html_content = _persist_timeline_safe_html(html_path, html_content)

        if final_report.get("denseCardHeavy") and len(final_issues) >= 1:
            _apply_dense_card_safe_mode(page)
            dense_card_safe_applied = True
            persisted_dense_card_safe = True
            final_report = _inspect_html_layout(page)
            final_issues = _summarize_layout_issues(final_report)
            html_content = _persist_dense_card_safe_html(html_path, html_content)

        if final_report.get("dualPanelCover") and len(final_issues) >= 1:
            _apply_dual_panel_cover_safe_mode(page)
            dual_panel_cover_safe_applied = True
            persisted_dual_panel_cover_safe = True
            final_report = _inspect_html_layout(page)
            final_issues = _summarize_layout_issues(final_report)
            html_content = _persist_dual_panel_cover_safe_html(html_path, html_content)

        if final_report.get("summaryHeavy") and (final_report.get("overlap") or len(final_issues) >= 2):
            _apply_summary_safe_mode(page)
            summary_safe_applied = True
            persisted_summary_safe = True
            final_report = _inspect_html_layout(page)
            final_issues = _summarize_layout_issues(final_report)
            html_content = _persist_summary_safe_html(html_path, html_content)

        if final_report.get("conclusionHeavy") and len(final_issues) >= 1:
            _apply_conclusion_safe_mode(page)
            conclusion_safe_applied = True
            persisted_conclusion_safe = True
            final_report = _inspect_html_layout(page)
            final_issues = _summarize_layout_issues(final_report)
            html_content = _persist_conclusion_safe_html(html_path, html_content)

        if final_report.get("stepCardHeavy") and len(final_issues) >= 1:
            _apply_step_card_safe_mode(page)
            step_card_safe_applied = True
            persisted_step_card_safe = True
            final_report = _inspect_html_layout(page)
            final_issues = _summarize_layout_issues(final_report)
            html_content = _persist_step_card_safe_html(html_path, html_content)

        compact_applied = False
        if final_issues and not _should_regenerate(final_report):
            _apply_compact_mode(page)
            compact_applied = True
            persisted_compact = True
            final_report = _inspect_html_layout(page)
            final_issues = _summarize_layout_issues(final_report)
            html_content = _persist_compact_html(html_path, html_content)

        png = page.screenshot(type="png", clip={
            "x": 0, "y": 0, "width": 1280, "height": 720,
        })
        browser.close()

    status = "pass"
    if final_issues:
        status = "regenerate" if _should_regenerate(final_report) else "compact_pass"

    return png, {
        "status": status,
        "compact_applied": compact_applied,
        "summary_safe_applied": summary_safe_applied,
        "timeline_safe_applied": timeline_safe_applied,
        "dense_card_safe_applied": dense_card_safe_applied,
        "dual_panel_cover_safe_applied": dual_panel_cover_safe_applied,
        "inline_panel_safe_applied": inline_panel_safe_applied,
        "cover_header_safe_applied": cover_header_safe_applied,
        "cover_chain_safe_applied": cover_chain_safe_applied,
        "signal_dark_cover_safe_applied": signal_dark_cover_safe_applied,
        "signal_dark_toc_safe_applied": signal_dark_toc_safe_applied,
        "signal_dark_ending_safe_applied": signal_dark_ending_safe_applied,
        "toc_safe_applied": toc_safe_applied,
        "conclusion_safe_applied": conclusion_safe_applied,
        "step_card_safe_applied": step_card_safe_applied,
        "persisted_compact": persisted_compact,
        "persisted_summary_safe": persisted_summary_safe,
        "persisted_timeline_safe": persisted_timeline_safe,
        "persisted_dense_card_safe": persisted_dense_card_safe,
        "persisted_dual_panel_cover_safe": persisted_dual_panel_cover_safe,
        "persisted_inline_panel_safe": persisted_inline_panel_safe,
        "persisted_cover_header_safe": persisted_cover_header_safe,
        "persisted_cover_chain_safe": persisted_cover_chain_safe,
        "persisted_signal_dark_cover_safe": persisted_signal_dark_cover_safe,
        "persisted_signal_dark_toc_safe": persisted_signal_dark_toc_safe,
        "persisted_signal_dark_ending_safe": persisted_signal_dark_ending_safe,
        "persisted_cover_sequence_fix": persisted_cover_sequence_fix,
        "persisted_toc_safe": persisted_toc_safe,
        "persisted_conclusion_safe": persisted_conclusion_safe,
        "persisted_step_card_safe": persisted_step_card_safe,
        "initial_issues": initial_issues,
        "final_issues": final_issues,
        "initial_report": initial_report,
        "final_report": final_report,
    }


def render_html_screenshot(html_path: Path) -> bytes:
    png, _ = render_html_with_validation(html_path)
    return png


def save_html_screenshot(html_path: Path, image_path: Path) -> Path:
    png_bytes = render_html_screenshot(html_path)
    image_path.write_bytes(png_bytes)
    return image_path


def write_slide_status(out_dir: Path, slide_status: dict) -> Path:
    status_path = out_dir / "slide-status.json"
    status_path.write_text(
        json.dumps({"slides": slide_status}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return status_path


def html_to_png_bytes(html_path: Path) -> bytes:
    """用 playwright 将 HTML 文件渲染为 1280×720 PNG。"""
    png, _ = render_html_with_validation(html_path)
    return png


def build_pptx(html_dir: Path, output_path: Path) -> Path:
    """将 HTML 目录中的所有 HTML 文件转换为 PPTX。"""
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank_layout = prs.slide_layouts[6]

    html_files = sorted(html_dir.glob("*.html"))
    if not html_files:
        raise ValueError(f"HTML 目录为空: {html_dir}")

    for html_path in html_files:
        print(f"  插入: {html_path.name}")
        slide = prs.slides.add_slide(blank_layout)
        try:
            png_bytes, report = render_html_with_validation(html_path)
            if report.get("toc_safe_applied"):
                print("    [检查] 检测到目录页留白过大，已应用 toc-safe mode")
            if report.get("timeline_safe_applied"):
                print("    [检查] 检测到时间线高风险布局，已应用 timeline-safe mode")
            if report.get("dense_card_safe_applied"):
                print("    [检查] 检测到高密度卡片布局，已应用 dense-card-safe mode")
            if report.get("cover_header_safe_applied"):
                print("    [检查] 检测到封面标题贴上边，已应用 cover-header-safe mode")
            if report.get("cover_chain_safe_applied"):
                print("    [检查] 检测到封面编号卡未垂直居中，已应用 cover-chain-safe mode")
            if report.get("summary_safe_applied"):
                print("    [检查] 检测到总结型高风险布局，已应用 summary-safe mode")
            if report.get("conclusion_safe_applied"):
                print("    [检查] 检测到结论页过挤布局，已应用 conclusion-safe mode")
            if report.get("step_card_safe_applied"):
                print("    [检查] 检测到步骤卡纵向超限，已应用 step-card-safe mode")
            if report["compact_applied"]:
                print("    [检查] 检测到轻微超限，已应用紧凑模式")
            if report.get("persisted_toc_safe"):
                print("    [检查] 已将 toc-safe 样式回写到 HTML 文件")
            if report.get("persisted_timeline_safe"):
                print("    [检查] 已将 timeline-safe 样式回写到 HTML 文件")
            if report.get("persisted_dense_card_safe"):
                print("    [检查] 已将 dense-card-safe 样式回写到 HTML 文件")
            if report.get("persisted_cover_header_safe"):
                print("    [检查] 已将 cover-header-safe 样式回写到 HTML 文件")
            if report.get("persisted_cover_chain_safe"):
                print("    [检查] 已将 cover-chain-safe 样式回写到 HTML 文件")
            if report.get("persisted_cover_sequence_fix"):
                print("    [检查] 已将封面序号感文案回写到 HTML 文件")
            if report.get("persisted_summary_safe"):
                print("    [检查] 已将 summary-safe 样式回写到 HTML 文件")
            if report.get("persisted_conclusion_safe"):
                print("    [检查] 已将 conclusion-safe 样式回写到 HTML 文件")
            if report.get("persisted_step_card_safe"):
                print("    [检查] 已将 step-card-safe 样式回写到 HTML 文件")
            if report.get("persisted_compact"):
                print("    [检查] 已将紧凑版样式回写到 HTML 文件")
            if report["final_issues"]:
                print(f"    [检查] 仍有 {len(report['final_issues'])} 个布局问题")
            slide.shapes.add_picture(
                io.BytesIO(png_bytes), left=0, top=0,
                width=SLIDE_W, height=SLIDE_H,
            )
        except Exception as e:
            print(f"  [警告] {html_path.name} 失败: {e}，跳过")

    prs.save(str(output_path))
    print(f"PPT 已保存: {output_path}")
    return output_path
