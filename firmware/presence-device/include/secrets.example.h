// 复制为 secrets.h（不进 git，见 .gitignore）后填入真实值。
#pragma once

#define WIFI_SSID     "你家WiFi"
#define WIFI_PASS     "密码"
#define BACKEND_HOST  "192.168.x.x"   // 后端主机局域网 IP（config.yaml admin.host=0.0.0.0 时局域网可达）
#define BACKEND_PORT  8080
#define BACKEND_PATH  "/ws/device"
#define AUTH_TOKEN    "emt_..."   // 后端 POST /auth/tokens {"label":"esp32-device","profile":"device"} 签发的
                                  // device profile token（仅 ws.device scope）；legacy admin.secret_key 仍兼容但不建议
