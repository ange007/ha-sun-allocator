#pragma once

#include "esphome.h"

namespace esphome {
namespace sunallocator_relay {

class SunAllocatorRelay : public Component, public FloatOutput {
 public:
  SunAllocatorRelay(GPIOPin *pin) : pin_(pin) {}

  void setup() override {
    pin_->setup();
    pin_->digital_write(false);
    
    // Initialize PWM
    this->set_frequency(1000);  // 1kHz PWM frequency
    this->zero_means_zero_ = true;
    
    // Set initial state
    this->write_state(0.0f);
  }

  void set_frequency(float frequency) {
    this->frequency_ = frequency;
    this->period_us_ = static_cast<uint32_t>(1e6f / this->frequency_);
  }

  void write_state(float state) override {
    if (state <= 0.0f) {
      // Turn off completely
      this->pin_->digital_write(false);
      this->high_freq_ = false;
      return;
    }

    // Constrain state to 0.0-1.0
    state = clamp(state, 0.0f, 1.0f);
    
    // Calculate duty cycle
    uint32_t duty_cycle = static_cast<uint32_t>(state * this->period_us_);
    
    // Apply PWM
    if (!this->high_freq_) {
      this->high_freq_ = true;
    }
    
    this->pin_->digital_write(true);
    delayMicroseconds(duty_cycle);
    this->pin_->digital_write(false);
    delayMicroseconds(this->period_us_ - duty_cycle);
  }

 protected:
  GPIOPin *pin_;
  float frequency_{1000.0f};  // Default 1kHz
  uint32_t period_us_{1000};  // Period in microseconds
  bool high_freq_{false};
  bool zero_means_zero_{false};
};

}  // namespace sunallocator_relay
}  // namespace esphome
