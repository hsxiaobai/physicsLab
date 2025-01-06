# -*- coding: utf-8 -*-
from random import choice
from string import ascii_lowercase, ascii_letters, digits

from collections import namedtuple
from .typehint import Tuple, Union, num_type

position = namedtuple("position", ["x", "y", "z"])

def round_data(num: num_type) -> num_type:
    if not isinstance(num, (int, float)):
        raise TypeError
    return round(num, 4)

# TODO 废弃该函数, 用round_data代替
def roundData(*num) -> Union[num_type, Tuple[num_type]]:
    if not all(isinstance(val, (int, float)) for val in num):
        raise TypeError

    if len(num) == 1:
        return round_data(num[0])
    return tuple(round_data(i) for i in num)

# 生成随机字符串
def randString(strLength: int, lower: bool = False) -> str:
    if not isinstance(strLength, int):
        raise TypeError

    if lower:
        letters = ascii_lowercase
    else:
        letters = ascii_letters
    return ''.join(choice(letters + digits) for _ in range(strLength))
