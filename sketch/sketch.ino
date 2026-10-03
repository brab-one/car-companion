// Microcontroller side of the Car Companion. It drives hardware only; all the
// logic is in Python (python/companion/), reached through the Bridge.
//
// Now: reads the Modulino Movement on the Qwiic connector and sends its
// samples to Python as "accel" (x, y, z in g). Works without the sensor too:
// it keeps looking for one every few seconds and tells Python ("motion_sensor").
// Later: the LED matrix (step 6) and the OLED renderer (see PROTOCOL.md, "Scenes").

#include <Arduino_RouterBridge.h>
#include <Arduino_Modulino.h>

ModulinoMovement movement;

const unsigned long SAMPLE_MS = 50;    // 20 samples a second are plenty for "is it shaken?"
const unsigned long RETRY_MS = 5000;   // how often to look for a sensor that is not there

bool sensorFound = false;
unsigned long lastSample = 0;
unsigned long lastTry = 0;

void setup() {
  Bridge.begin();
  Modulino.begin(Wire1);  // the Qwiic connector
  sensorFound = movement.begin();
  lastTry = millis();
}

void loop() {
  unsigned long now = millis();

  if (!sensorFound) {
    if (now - lastTry >= RETRY_MS) {
      lastTry = now;
      sensorFound = movement.begin();
      Bridge.notify("motion_sensor", sensorFound);
    }
    return;
  }

  if (now - lastSample >= SAMPLE_MS) {
    lastSample = now;
    if (movement.update() == 1) {
      Bridge.notify("accel", movement.getX(), movement.getY(), movement.getZ());
    }
  }
}
