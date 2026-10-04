// Microcontroller side of the Car Companion. It drives hardware only; all the
// logic is in Python (python/companion/), reached through the Bridge.
//
// Now: resting eyes on the board's LED matrix, blinking now and then. Before
// the sketch runs (it waits for Linux), the microcontroller's boot animation
// shows the same eyes (tools/boot_eyes.py). Reads the Modulino Movement on the
// Qwiic connector and sends its samples to Python as "accel" (x, y, z in g).
// Works without the sensor too: it keeps looking for one every few seconds and
// tells Python ("motion_sensor").
// Later: the LED matrix shows the app's scenes (step 6), and the OLED renderer
// (see PROTOCOL.md, "Scenes").

#include <Arduino_RouterBridge.h>
#include <Arduino_Modulino.h>
#include <Arduino_LED_Matrix.h>

ModulinoMovement movement;
Arduino_LED_Matrix matrix;

const unsigned long SAMPLE_MS = 50;    // 20 samples a second are plenty for "is it shaken?"
const unsigned long RETRY_MS = 5000;   // how often to look for a sensor that is not there

bool sensorFound = false;
unsigned long lastSample = 0;
unsigned long lastTry = 0;

// ---- eyes on the 13 x 8 LED matrix -----------------------------------------------
// tools/boot_eyes.py draws the same eyes for the boot animation: change both.

const int COLS = 13, ROWS = 8;
const int EYE_COLS[] = {2, 8};       // first column of each eye; each is 3 wide
const uint8_t LIT = 7, CORNER = 2;   // brightness 0..7; dim corners make them look round
const int OPEN_TOP = 2, OPEN_BOTTOM = 6;
const int BLINK[][2] = {{3, 5}, {4, 4}, {4, 4}, {3, 5}};  // top and bottom row, BLINK_MS each
const int BLINK_STEPS = sizeof(BLINK) / sizeof(BLINK[0]);
const unsigned long BLINK_MS = 45;

uint8_t frame[ROWS * COLS];
unsigned long eyesAt = 0;            // when the eyes last changed
unsigned long eyesWait = 0;          // how long they stay like that
int blinkStep = BLINK_STEPS;         // BLINK_STEPS: open

void drawEyes(int top, int bottom) {
  memset(frame, 0, sizeof(frame));
  bool round = bottom - top >= 3;
  for (int first : EYE_COLS) {
    for (int row = top; row <= bottom; row++) {
      for (int col = first; col < first + 3; col++) {
        bool corner = round && (row == top || row == bottom) && col != first + 1;
        frame[row * COLS + col] = corner ? CORNER : LIT;
      }
    }
  }
  matrix.draw(frame);
}

void updateEyes(unsigned long now) {
  if (now - eyesAt < eyesWait) {
    return;
  }
  eyesAt = now;
  blinkStep = blinkStep == BLINK_STEPS ? 0 : blinkStep + 1;
  if (blinkStep < BLINK_STEPS) {
    drawEyes(BLINK[blinkStep][0], BLINK[blinkStep][1]);
    eyesWait = BLINK_MS;
  } else {
    drawEyes(OPEN_TOP, OPEN_BOTTOM);
    eyesWait = random(2000, 6000);
  }
}

// How long the microcontroller has been running, to see from Linux when the
// sketch started (README, "Fast start").
unsigned long uptimeMs() {
  return millis();
}

void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(3);
  drawEyes(OPEN_TOP, OPEN_BOTTOM);
  eyesWait = random(2000, 6000);

  Bridge.begin();
  Bridge.provide("uptime_ms", uptimeMs);
  Modulino.begin(Wire1);  // the Qwiic connector
  sensorFound = movement.begin();
  lastTry = millis();
}

void loop() {
  unsigned long now = millis();
  updateEyes(now);

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
