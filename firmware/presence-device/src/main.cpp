#include <Arduino.h>

#include "display.h"
#include "ws_client.h"

void setup() {
    Serial.begin(115200);
    displaySetup();
    wsClientSetup();
    Serial.println("presence-device 启动完成");
}

void loop() {
    wsClientLoop();
    displayTick();
}
