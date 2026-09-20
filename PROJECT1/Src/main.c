/* USER CODE BEGIN Header */
/* USER CODE END Header */

#include "main.h"

/* USER CODE BEGIN Includes */
#include "mpu6050.h"
#include "max30102.h"
#include "bme68x.h"
#include "bme68x_stm32.h"
#include "ds18b20.h"
#include <stdio.h>
#include <string.h>
/* USER CODE END Includes */

ADC_HandleTypeDef hadc1;
I2C_HandleTypeDef hi2c1;
UART_HandleTypeDef huart1;

/* USER CODE BEGIN PV */
uint32_t ecg_value = 0;
MPU6050_t mpu_data;

uint32_t ir_data = 0;
uint32_t red_data = 0;
uint32_t heart_rate = 0;

float body_temperature = 0.0;

struct bme68x_dev bme;
struct bme68x_data bme_data;
uint8_t n_fields;

char tx_buffer[128];
/* USER CODE END PV */

void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_I2C1_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_ADC1_Init(void);

/* USER CODE BEGIN PFP */
/* USER CODE END PFP */

/* USER CODE BEGIN 0 */
uint32_t calculate_bpm(uint32_t raw_ir_value) {
    static uint32_t last_beat_time = 0;
    static int32_t threshold = 100000;
    uint32_t current_time = HAL_GetTick();
    uint32_t bpm = 0;

    if (raw_ir_value > threshold) {
        uint32_t delta = current_time - last_beat_time;
        if (delta > 300 && delta < 2000) {
            bpm = 60000 / delta;
            last_beat_time = current_time;
        }
    }
    threshold = (threshold * 99 + raw_ir_value) / 100;
    return bpm;
}
/* USER CODE END 0 */

int main(void)
{
  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();
  MX_I2C1_Init();
  MX_USART1_UART_Init();
  MX_ADC1_Init();

  /* USER CODE BEGIN 2 */
  MPU6050_Init(&hi2c1);
  MAX30102_Init(&hi2c1);
  DS18B20_Init();

  bme.intf = BME68X_I2C_INTF;
  bme.read = bme68x_i2c_read;
  bme.write = bme68x_i2c_write;
  bme.delay_us = bme68x_delay_us;
  bme.intf_ptr = (void*)(intptr_t)BME68X_I2C_ADDR_LOW;
  bme.amb_temp = 25;
  bme68x_init(&bme);
  /* USER CODE END 2 */

  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    HAL_ADC_Start(&hadc1);
    if (HAL_ADC_PollForConversion(&hadc1, 10) == HAL_OK) {
        ecg_value = HAL_ADC_GetValue(&hadc1);
    }
    HAL_ADC_Stop(&hadc1);

    MPU6050_Read_All(&hi2c1, &mpu_data);

    MAX30102_Read(&hi2c1, &ir_data, &red_data);
    if (ir_data > 50000) {
        heart_rate = calculate_bpm(ir_data);
    } else {
        heart_rate = 0;
    }

    bme68x_get_data(BME68X_FORCED_MODE, &bme_data, &n_fields, &bme);

    body_temperature = DS18B20_Read();

    sprintf(tx_buffer, "ECG: %lu | HR: %lu | Temp: %.1f | MPU-X: %d\r\n",
            ecg_value, heart_rate, body_temperature, (int)mpu_data.Accel_X_RAW);

    HAL_UART_Transmit(&huart1, (uint8_t*)tx_buffer, strlen(tx_buffer), 100);

    HAL_Delay(50);
  }
  /* USER CODE END 3 */
}
