# подключение необходимых зависимостей
import json
import numpy as np
from flask import Flask, request
from scipy.optimize import minimize
from werkzeug.serving import WSGIRequestHandler
from config import Config

app = Flask(__name__)


# класс для хранения значения выделяемой тепловой мощности в момент времени x
class Point:
    def __init__(self, time, value):
        self.time = time
        self.value = value

    def serialize(self):
        return {"time": self.time, "value": self.value}


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
# макимальный сдвиг оборудования
MAX_OFFSET = 14.
# минимальный сдвиг оборудования
MIN_OFFSET = -14.
# структура данных для хранения оборудования
equipment = {}
# структура данных для хранения смещений
offsets = {}


# функция для рассчёта минимального тепловыделения от группы оборудования в зависимости от их смещения
def getMinimumThermalPower(local_offsets):
    # тепловая характеристика всего оборудования
    equipmentQ = []
    # просматриваем каждое оборудование
    for key in equipment:
        y = [j.value for j in equipment[key]]
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
    # получаем тепловую мощность за весь период работы оборудования
    return Qmin


# целевая функция - максимизация минимального тепловыделения за весь период работы оборудования
def objectiveFunction(local_offsets):
    local_offsets = [round(i) for i in local_offsets]
    offsets_dict = convertOffsetsToDict(local_offsets, equipment.keys())
    Qmin = getMinimumThermalPower(offsets_dict)
    return -min(Qmin)


# поиск оптимальных смещений оборудования
def optimize():
    # список ограничений, накладываемых на переменные
    restrictions = []
    for i in range(0, len(offsets)):
        restrictions.append((MIN_OFFSET, MAX_OFFSET))
    # начальное смещение оборудования
    x0 = []
    for i in range(len(offsets)):
        x0.append(0.)
    # применяем метод Пауэлла для минимизации целевой функции (решается обратная задача)
    result = minimize(objectiveFunction, x0=np.array(x0), method='powell', bounds=restrictions)
    # округляем смещения
    resultX = [round(i) for i in result.x]
    # получаем минимальное значение тепловыделений группы оборудования за весь период работы
    resultY = -result.fun
    return resultX, resultY


@app.route('/v1/getMinimumThermalPower', methods=['POST'])
def getMinimumThermalPowerRoute():
    try:
        request_data = request.get_json()
        global TIME_PERIOD
        try:
            TIME_PERIOD = int(request_data['period'])
        except Exception:
            pass
        equipmentObj = request_data['equipment']
        for e in equipmentObj:
            offsets[e['id']] = e['offset']
            equipment[e['id']] = []
            for d in e['data']:
                equipment[e['id']].append(Point(float(d['time']), float(d['value'])))

        result = getMinimumThermalPower(offsets)
        points = [Point(round(result[i], 2), i) for i in range(0, TIME_PERIOD)]
        result_dict = {}
        result_dict['data'] = [i.serialize() for i in points]
        result_dict['min_value'] = round(min(result), 2)
        result_dict['period'] = TIME_PERIOD
        response = app.response_class(
            response=json.dumps(result_dict,
                                ensure_ascii=False,
                                default=str),
            status=200,
            mimetype='application/json'
        )
        return response
    except KeyError as e:
        response = app.response_class(
            response=f'{{"code":400, "message":"Not found property {e}"}}',
            status=400,
            mimetype='application/json'
        )
        return response
    except Exception as e:
        response = app.response_class(
            response=f'{{"code":400, "message":"Invalid request"}}',
            status=400,
            mimetype='application/json'
        )
        return response


@app.route('/v1/optimize', methods=['POST'])
def optimizeRoute():
    try:
        request_data = request.get_json()
        global TIME_PERIOD
        try:
            TIME_PERIOD = int(request_data['period'])
        except Exception:
            pass
        equipmentObj = request_data['equipment']
        for e in equipmentObj:
            try:
                offsets[e['id']] = e['offset']
            except Exception:
                pass
            equipment[e['id']] = []
            for d in e['data']:
                equipment[e['id']].append(Point(float(d['time']), float(d['value'])))

        result = optimize()
        offsets_dict = convertOffsetsToDict(result[0], offsets.keys())
        offsets_list = []
        for offset in offsets_dict:
            offset_dict = {}
            offset_dict['key'] = offset
            offset_dict['value'] = offsets_dict[offset]
            offsets_list.append(offset_dict)
        result_dict = {}
        result_dict['offsets'] = offsets_list
        result_dict['min_value'] = round(result[1], 2)
        result_dict['period'] = TIME_PERIOD
        response = app.response_class(
            response=json.dumps(result_dict,
                                ensure_ascii=False,
                                default=str),
            status=200,
            mimetype='application/json'
        )
        return response
    except KeyError as e:
        response = app.response_class(
            response=f'{{"code":400, "message":"Not found property {e}"}}',
            status=400,
            mimetype='application/json'
        )
        return response
    except Exception as e:
        response = app.response_class(
            response=f'{{"code":400, "message":"Invalid request"}}',
            status=400,
            mimetype='application/json'
        )
        return response


if __name__ == '__main__':
    WSGIRequestHandler.protocol_version = "HTTP/1.1"
    app.run(debug=Config.debug, host=Config.host_url, port=Config.host_port)
