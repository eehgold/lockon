#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

const byte PCA9685_ADDRESS = 0x40;
const byte SERVO_Y_CHANNEL = 0;
const byte SERVO_X_CHANNEL = 1;

const int SERVO_MIN_US = 1250;
const int SERVO_CENTER_US = 1500;
const int SERVO_MAX_US = 1750;
const int POSITION_MIN = -100;
const int POSITION_CENTER = 0;
const int POSITION_MAX = 100;

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(PCA9685_ADDRESS);
bool pcaFound = false;
int currentX = POSITION_CENTER;
int currentY = POSITION_CENTER;

byte i2cProbe(byte address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission();
}

bool i2cDevicePresent(byte address) {
  return i2cProbe(address) == 0;
}

void scanI2C() {
  Serial.println("Scan I2C en cours...");

  byte foundCount = 0;
  for (byte address = 1; address < 127; address++) {
    if (i2cDevicePresent(address)) {
      Serial.print("  Peripherique trouve a 0x");
      if (address < 16) {
        Serial.print("0");
      }
      Serial.println(address, HEX);
      foundCount++;
    }
  }

  if (foundCount == 0) {
    Serial.println("  Aucun peripherique I2C trouve.");
  }
}

void initPCA9685() {
  Serial.println("PCA9685 detecte a l'adresse 0x40.");

  pwm.begin();
  pwm.setOscillatorFrequency(27000000);
  pwm.setPWMFreq(50);
  delay(10);

  pwm.writeMicroseconds(SERVO_X_CHANNEL, SERVO_CENTER_US);
  pwm.writeMicroseconds(SERVO_Y_CHANNEL, SERVO_CENTER_US);
  Serial.println("Servos initialises au centre.");
  Serial.println("Pret. Commande attendue: POS x y");
}

int positionToPulse(int position) {
  position = constrain(position, POSITION_MIN, POSITION_MAX);
  return map(position, POSITION_MIN, POSITION_MAX, SERVO_MIN_US, SERVO_MAX_US);
}

void setTurretPosition(int x, int y) {
  currentX = constrain(x, POSITION_MIN, POSITION_MAX);
  currentY = constrain(y, POSITION_MIN, POSITION_MAX);

  pwm.writeMicroseconds(SERVO_X_CHANNEL, positionToPulse(currentX));
  pwm.writeMicroseconds(SERVO_Y_CHANNEL, positionToPulse(currentY));

  Serial.print("OK X=");
  Serial.print(currentX);
  Serial.print(" Y=");
  Serial.println(currentY);
}

void handleSerialCommand(String command) {
  command.trim();
  command.toUpperCase();

  if (command.length() == 0) {
    return;
  }

  if (command == "CENTER") {
    setTurretPosition(POSITION_CENTER, POSITION_CENTER);
    return;
  }

  if (command.startsWith("POS ")) {
    int firstSpace = command.indexOf(' ');
    int secondSpace = command.indexOf(' ', firstSpace + 1);
    if (secondSpace < 0) {
      Serial.println("ERR format attendu: POS x y");
      return;
    }

    int x = command.substring(firstSpace + 1, secondSpace).toInt();
    int y = command.substring(secondSpace + 1).toInt();
    setTurretPosition(x, y);
    return;
  }

  Serial.println("ERR commande inconnue");
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  Serial.begin(115200);
  delay(2000);

  Serial.println();
  Serial.println("LOCKON - test PCA9685 + servos");
  Serial.println("Moniteur serie: 115200 bauds");

  Serial.println("Initialisation I2C...");
  Wire.begin();
#if defined(WIRE_HAS_TIMEOUT)
  Wire.setWireTimeout(25000, true);
  Serial.println("Timeout I2C actif.");
#else
  Serial.println("Timeout I2C non disponible avec ce core Arduino.");
#endif

  Serial.println("Recherche du PCA9685 a l'adresse 0x40...");
  byte pcaStatus = i2cProbe(PCA9685_ADDRESS);
  pcaFound = pcaStatus == 0;
  if (!pcaFound) {
    Serial.println("ERREUR: PCA9685 absent a l'adresse 0x40.");
    Serial.print("Code I2C: ");
    Serial.println(pcaStatus);
    Serial.println("Verifier A4/SDA, A5/SCL, VCC, GND et masse commune.");
    scanI2C();
    return;
  }

  initPCA9685();
}

void loop() {
  if (!pcaFound) {
    delay(3000);
    scanI2C();
    pcaFound = i2cDevicePresent(PCA9685_ADDRESS);
    if (pcaFound) {
      initPCA9685();
    }
    return;
  }

  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    handleSerialCommand(command);
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
  }
}
