"""
THIS IS NOT PART OF THE PROGRAM
lowk js me messing abt :)
"""

import time
import random

level1 = 1
level2 = 1
level3 = 1
level4 = 1
level5 = 1

def slow_print(text, delay=0.1):
    for char in text:
        print(char, end='', flush=True)
        time.sleep(delay)
    print()

class Captcha:
    def __init__(self, length=random.randint(100, 500)):
        self.length = length
        self.captcha = self.generate_captcha()

    def generate_captcha(self):
        characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
        captcha = ''.join(random.choice(characters) for _ in range(self.length))
        return captcha

    def display_captcha(self):
        print(f"Captcha: {self.captcha}")

    def validate_captcha(self, user_input):
        return user_input == self.captcha

question2 = """f(x) = ax3 + 10x2 − 3ax − 4
Given that (x − 1) is a factor of f(x), find the value of the constant a."""

def level_2():
    slow_print("Welcome to Level 2!", delay=0.05)
    slow_print("In this level, you will be asked to solve a simple math problem.", delay=0.05)
    answer = "false"
    while answer == "false":
        slow_print("Please solve the following problem:", delay=0.05)
        print("")
        slow_print(question2, delay=0.05)
        level2_answer = int(input("ANSWER: "))
        if level2_answer == 3:
            slow_print("Correct! You have completed Level 2.", delay=0.05)
            answer = "correct"
            level2 = "done"
            
        else:
            slow_print("Incorrect answer. Please try again.", delay=0.05)
            answer = "false"

def main():
    captcha = Captcha()
    captcha.display_captcha()

    print("")
    slow_print("Please enter the captcha displayed above.", delay=0.05)
    user_input = input("ANSWER: ")
    if captcha.validate_captcha(user_input):
        slow_print("Captcha validated successfully!", delay=0.05)
        print("")
        level1 = "done"
        level_2()
    else:
        slow_print("Invalid captcha. Please try again.", delay=0.05)

if __name__ == "__main__":
    main()
