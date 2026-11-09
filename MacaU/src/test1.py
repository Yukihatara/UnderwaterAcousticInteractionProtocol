from termcolor import colored

print(colored("Красный", "red"))
print(colored("Зелёный на белом", "green", "on_white"))
print(colored("Жирный синий", "blue", attrs=["bold"]))
