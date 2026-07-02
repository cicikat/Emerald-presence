// display — U8g2 中文分段+流式渲染 + 爱心动作。
// 硬件（SSD1306 128x64 I2C，SDA=5/SCL=6，addr 0x3C）照抄 Emerald-hello。
// hello 未渲染过中文；u8g2_font_wqy12_t_gb2312 是 Part 3.4 决策落地的中文字库方案。
#pragma once

#include <Arduino.h>

#include "ws_client.h"

void displaySetup();

// 每帧调用一次：驱动分段自动翻页、爱心倒计时结束后恢复文字、离线状态渲染。
void displayTick();

void displaySetConnState(ConnState state);

// 3.4 状态机
void displayStreamStart(const String &msgId);
void displayStreamDelta(const String &msgId, const String &delta);
void displayStreamEnd(const String &msgId);
void displaySegments(const String &msgId, const String &content);      // message_segments.content
void displayChannelMessage(const String &msgId, const String &content); // 主动消息，无流式

// 3.5 爱心动作。durationMs<=0 时使用默认值。
void displayShowHeart(int durationMs);
