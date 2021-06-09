# подключение необходимых зависимостей
import csv
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize


# класс для хранения значения выделяемой тепловой мощности в момент времени x
class Point:
    def __init__(self, x_init, y_init):
        self.x = x_init
        self.y = y_init


# функция чтения данных их CSV-файла
def parseCSV(csv_path):
    local_equipment = {}
    with open(csv_path, "r") as fileObj:
        reader = csv.reader(fileObj, delimiter=';')
        # пропускаем заголовок CSV-файла
        next(reader, None)
        # просматриваем каждую строку файла
        for row in reader:
            # если найдено новое оборудование
            if local_equipment.get(int(row[0])) is None:
                local_equipment[int(row[0])] = [Point(float(row[1]), float(row[2]))]
            # если добавляем данные в уже существующую запись
            else:
                local_equipment[int(row[0])].append(Point(float(row[1]), float(row[2])))
    return local_equipment


# функция конвертации списка смещений оборудования к словарю
def convertOffsetsToDict(local_offsets, keys):
    offsets_dict = {}
    index = 0
    for key in keys:
        offsets_dict[key] = local_offsets[index]
        index += 1
    return offsets_dict


# период работы группы оборудования
TIME_PERIOD = 48
# формируем структуру данных для хранения оборудования
equipment = parseCSV("SourceData.csv")
# получаем данные о текущих смещениях
offsetsValues = [0, -6, 9, -15, -12, 7, 12, -3]
# offsets = [0, -6, 9, -12, 7, 12, -3]
# offsets = [-16, -13, -13, -5, 4, -9, 1, -5]
offsets = convertOffsetsToDict(offsetsValues, equipment.keys())


# функция для рассчёта минимального тепловыделения группы оборудования в зависимости от их смещения
def getMinimumThermalPower(local_offsets):
    # тепловая характеристика всего оборудования
    equipmentQ = []
    # просматриваем каждое оборудование
    for key in equipment:
        y = [j.y for j in equipment[key]]
        # списки для хранения тепловой характеристики оборудования
        x_period = []
        y_period = []
        # смещение текущего оборудования
        current_offset = local_offsets[key]
        index = -current_offset
        # формируем тепловую характеристику оборудования за весь период работы
        for i in range(TIME_PERIOD):
            x_period.append(i)
            if index < 0:
                y_period.append(0)
                index += 1
            else:
                y_period.append(y[index])
                if index == len(y) - 1:
                    index = 0
                else:
                    index += 1
        # формируем тепловую характеристику оборудования до начала действия плана оптимизации
        index = -current_offset
        x_pre_period = []
        y_pre_period = []
        for i in range(max(min(local_offsets) + 1, -24), 0):
            x_pre_period.append(i)
            if current_offset >= 0:
                y_pre_period.insert(0, 0)
            else:
                y_pre_period.insert(0, y[index - 1])
                if index - 1 != 0:
                    index -= 1
                else:
                    current_offset = 1
        x_period = x_pre_period + x_period
        y_period = y_pre_period + y_period
        # лямбда-функция для получения значения тепловой мощности в любой момент времени
        Qt = lambda t: np.interp(t, x_period, y_period)
        equipmentQ.append([Qt(i) for i in range(0, TIME_PERIOD + 1)])
    # тепловая мощность, выделяемая каждый час от всего оборудования
    Qmin = []
    for i in range(0, TIME_PERIOD):
        sum = 0
        for j in range(0, len(equipmentQ)):
            sum += equipmentQ[j][i]
        Qmin.append(sum)
    # получаем минимальную тепловую мощность за весь период работы оборудования
    return Qmin


# выводим результат
result = getMinimumThermalPower(offsets)
# получаем минимальную тепловую мощность за весь период работы оборудования
resultMin = min(result)
print(f'Текущее значение целевой функции: {resultMin}')

plt.plot([i for i in range(0, TIME_PERIOD)], result)
plt.plot([i for i in range(0, TIME_PERIOD)], [resultMin for i in range(0, TIME_PERIOD)])
plt.show()


# целевая функция - максимизация минимального тепловыделения за весь период работы оборудования
def objectiveFunction(local_offsets):
    local_offsets = [round(i) for i in local_offsets]
    offsets_dict = convertOffsetsToDict(local_offsets, equipment.keys())
    Qmin = getMinimumThermalPower(offsets_dict)
    return -min(Qmin)


# список ограничений, накладываемых на переменные
restrictions = []
for i in range(0, len(offsets)):
    restrictions.append((-14., 14.))
# начальное смещение оборудования
x0 = []
for i in range(len(offsets)):
    x0.append(0.)

# применяем метод Паулла для минимизации целевой функции (решается обратная задача)
result = minimize(objectiveFunction, x0=np.array(x0), method='powell', bounds=restrictions)
# округляем смещения
resultX = [round(i) for i in result.x]
# получаем минимальное значение тепловыделений группы оборудования за весь период работы
resultY = -result.fun
print(f'Оптимальные смещения: {resultX}')
print(f'Значение целевой функции: {resultY}')

plt.plot([i for i in range(0, TIME_PERIOD)], getMinimumThermalPower(convertOffsetsToDict(resultX, offsets.keys())))
plt.plot([i for i in range(0, TIME_PERIOD)], [resultY for i in range(0, TIME_PERIOD)])
plt.show()
