# -*- coding: utf-8 -*-
import os
import copy
import json

from . import _tools
from . import errors
from . import savTemplate
from .web import User
from .savTemplate import Generate
from .circuit.wire import Wire, Pin
from .enums import ExperimentType, Category
from ._core import _Experiment, _ExperimentStack, OpenMode, _check_not_closed, _ElementBase
from .typehint import num_type, Optional, Union, List, overload, Tuple, Dict, Self

def crt_element(
        experiment: _Experiment,
        name: str,
        x: num_type = 0,
        y: num_type = 0,
        z: num_type = 0,
        elementXYZ: Optional[bool] = None,
        *args,
        **kwargs
) -> _ElementBase:
    ''' 通过元件的ModelID或其类名创建元件 '''
    if not isinstance(name, str) or \
            not isinstance(x, (int, float)) or \
            not isinstance(y, (int, float)) or \
            not isinstance(z, (int, float)):
        raise TypeError

    from physicsLab import circuit

    name = name.strip().replace(' ', '_').replace('-', '_')
    x, y, z = _tools.roundData(x, y, z) # type: ignore

    if experiment.experiment_type == ExperimentType.Circuit:
        if (name == '555_Timer'):
            return circuit.NE555(x, y, z, elementXYZ)
        elif (name == '8bit_Input'):
            return circuit.eight_bit_Input(x, y, z, elementXYZ)
        elif (name == '8bit_Display'):
            return circuit.eight_bit_Display(x, y, z, elementXYZ)
        else:
            return eval(f"circuit.{name}({x}, {y}, {z}, {elementXYZ}, *{args}, **{kwargs})")
    elif experiment.experiment_type == ExperimentType.Celestial:
        from physicsLab import celestial
        return eval(f"celestial.{name}({x}, {y}, {z})")
    elif experiment.experiment_type == ExperimentType.Electromagnetism:
        from physicsLab import electromagnetism
        return eval(f"electromagnetism.{name}({x}, {y}, {z})")
    else:
        assert False

def _get_all_pl_sav() -> List[str]:
    ''' 获取所有物实存档的文件名 '''
    savs = [i for i in os.walk(_Experiment.SAV_PATH_DIR)][0][-1]
    return [aSav for aSav in savs if aSav.endswith('.sav')]

def _open_sav(sav_path) -> dict:
    ''' 打开一个存档, 返回存档对应的dict
        @param sav_path: 存档的绝对路径
    '''
    def encode_sav(path: str, encoding: str) -> Optional[dict]:
        try:
            with open(path, encoding=encoding) as f:
                d = json.loads(f.read().replace('\n', ''))
        except (json.decoder.JSONDecodeError, UnicodeDecodeError): # 文件不是物实存档
            return None
        else:
            return d

    assert os.path.exists(sav_path)

    res = encode_sav(sav_path, "utf-8")
    if res is not None:
        return res

    try:
        import chardet # type: ignore
    except ImportError:
        for encoding in ("utf-8-sig", "gbk"):
            res = encode_sav(sav_path, encoding)
            if res is not None:
                return res
    else:
        with open(sav_path, "rb") as f:
            encoding = chardet.detect(f.read())["encoding"]
        res = encode_sav(sav_path, encoding)
        if res is not None:
            return res

    raise errors.InvalidSavError

def search_experiment(sav_name: str) -> Tuple[Optional[str], Optional[dict]]:
    ''' 检测实验是否存在
        @param sav_name: 存档名

        若存在则返回存档对应的文件名, 若不存在则返回None
    '''
    for aSav in _get_all_pl_sav():
        try:
            sav = _open_sav(os.path.join(_Experiment.SAV_PATH_DIR, aSav))
        except errors.InvalidSavError:
            continue
        if sav["InternalName"] == sav_name:
            return aSav, sav

    return None, None

class Experiment(_Experiment):
    @overload
    def __init__(self, open_mode: OpenMode, sav_name: str) -> None:
        ''' 根据存档名打开存档
            @open_mode = OpenMode.open_from_sav_name
            @sav_name: 存档的名字
        '''

    @overload
    def __init__(self, open_mode: OpenMode, filepath: str) -> None:
        ''' 根据存档对应的文件路径打开存档
            @open_mode = OpenMode.open_from_abs_path
            @filepath: 存档对应的文件的完整路径
        '''

    @overload
    def __init__(self, open_mode: OpenMode, content_id: str, category: Category, /, *, user: User = User()) -> None:
        ''' 从物实服务器中获取存档
            @open_mode = OpenMode.open_from_plar_app
            @content_id: 物实 实验/讨论 的id
            @category: 实验区还是黑洞区
            @user: 执行获取实验操作的用户, 若未指定则会创建一个临时匿名用户执行该操作 (会导致程序变慢)
        '''

    @overload
    def __init__(
            self,
            open_mode: OpenMode,
            sav_name: str,
            experiment_type: ExperimentType,
            /, *,
            force_crt: bool = False
    ) -> None:
        ''' 创建一个新实验
            @open_mode = OpenMode.crt
            @sav_name: 存档的名字
            @experiment_type: 实验类型
            @force_crt: 强制创建一个实验, 若已存在则覆盖已有实验
        '''

    def __init__(self, open_mode: OpenMode, *args, **kwargs) -> None:
        if not isinstance(open_mode, OpenMode) or len(args) == 0:
            raise TypeError

        self.open_mode: OpenMode = open_mode
        # 通过坐标索引元件; key: self._position, value: List[self...]
        self._elements_position: Dict[tuple, list] = {}
        # 通过index（元件生成顺序）索引元件
        self.Elements: List["_ElementBase"] = []

        # 尽管读取存档时会将元件的字符串一并读入, 但只有在调用 load_elements 将元件的信息
        # 导入self.Elements与self._element_position之后, 元件信息才被完全导入
        if open_mode == OpenMode.load_by_filepath:
            sav_name, *rest = args
            if not isinstance(sav_name, str) or len(rest) != 0:
                raise TypeError

            self.SAV_PATH = os.path.abspath(sav_name)

            if not os.path.exists(self.SAV_PATH):
                raise FileNotFoundError(f"\"{self.SAV_PATH}\" not found")
            if _ExperimentStack.inside(self):
                raise errors.ExperimentOpenedError

            _temp = _open_sav(self.SAV_PATH)

            if "Experiment" in _temp.keys():
                self.PlSav = _temp
            else: # 读取物实导出的存档只含有.sav的Experiment部分
                if _temp["Type"] == ExperimentType.Circuit.value:
                    self.PlSav = copy.deepcopy(savTemplate.Circuit)
                elif _temp["Type"] == ExperimentType.Celestial.value:
                    self.PlSav = copy.deepcopy(savTemplate.Celestial)
                elif _temp["Type"] == ExperimentType.Electromagnetism.value:
                    self.PlSav = copy.deepcopy(savTemplate.Electromagnetism)
                else:
                    assert False

                self.PlSav["Experiment"] = _temp
            self.__load()
        elif open_mode == OpenMode.load_by_sav_name:
            sav_name, *rest = args
            if not isinstance(sav_name, str) or len(rest) != 0:
                raise TypeError

            filename, _plsav = search_experiment(sav_name)
            if filename is None:
                raise errors.ExperimentNotExistError(f'No such experiment "{sav_name}"')

            self.SAV_PATH = os.path.join(_Experiment.SAV_PATH_DIR, filename)
            if _ExperimentStack.inside(self):
                raise errors.ExperimentOpenedError

            assert _plsav is not None
            self.PlSav = _plsav
            self.__load()
        elif open_mode == OpenMode.load_by_plar_app:
            content_id, category, *rest = args

            if not isinstance(content_id, str) or not isinstance(category, Category) or len(rest) != 0:
                raise TypeError
            user = kwargs.get("user", User())
            if not isinstance(user, User):
                raise TypeError

            self.SAV_PATH = os.path.join(_Experiment.SAV_PATH_DIR, f"{content_id}.sav")
            if _ExperimentStack.inside(self):
                    raise errors.ExperimentOpenedError

            _summary = user.get_summary(content_id, category)["Data"]
            del _summary["$type"]
            _experiment = user.get_experiment(_summary["ContentID"])["Data"]
            del _experiment["$type"]

            if _experiment["Type"] == ExperimentType.Circuit.value:
                self.PlSav = copy.deepcopy(savTemplate.Circuit)
            elif _experiment["Type"] == ExperimentType.Celestial.value:
                self.PlSav = copy.deepcopy(savTemplate.Celestial)
            elif _experiment["Type"] == ExperimentType.Electromagnetism.value:
                self.PlSav = copy.deepcopy(savTemplate.Electromagnetism)
            else:
                assert False

            self.PlSav["Experiment"] = _experiment
            self.PlSav["Summary"] = _summary
            self.__load()
        elif open_mode == OpenMode.crt:
            sav_name, experiment_type, *rest = args

            if not isinstance(sav_name, str) or \
                    not isinstance(experiment_type, ExperimentType) or \
                    len(rest) != 0:
                raise TypeError
            force_crt = kwargs.get("force_crt", False)
            if not isinstance(force_crt, bool):
                raise TypeError

            filepath, _ = search_experiment(sav_name)
            if not force_crt and filepath is not None:
                raise errors.ExperimentExistError
            elif force_crt and filepath is not None:
                # TODO 要是在一个force_crt的实验中又force_crt这个实验呢？
                path = os.path.join(_Experiment.SAV_PATH_DIR, filepath)
                os.remove(path)
                if os.path.exists(path.replace(".sav", ".jpg")): # 用存档生成的实验无图片，因此可能删除失败
                    os.remove(path.replace(".sav", ".jpg"))

            self.experiment_type = experiment_type
            self.SAV_PATH = os.path.join(_Experiment.SAV_PATH_DIR, f"{_tools.randString(34)}.sav")

            if self.experiment_type == ExperimentType.Circuit:
                self.is_elementXYZ: bool = False
                # 元件坐标系的坐标原点
                self.elementXYZ_origin_position: _tools.position = _tools.position(0, 0, 0)
                self.PlSav: dict = copy.deepcopy(savTemplate.Circuit)
                self.Wires: set = set() # Set[Wire] # 存档对应的导线
                # 存档对应的StatusSave, 存放实验元件，导线（如果是电学实验的话）
                self.CameraSave: dict = {
                    "Mode": 0, "Distance": 2.7, "VisionCenter": Generate, "TargetRotation": Generate
                }
                self.VisionCenter: _tools.position = _tools.position(0, -0.45, 1.08)
                self.TargetRotation: _tools.position = _tools.position(50, 0, 0)
            elif self.experiment_type == ExperimentType.Celestial:
                self.PlSav: dict = copy.deepcopy(savTemplate.Celestial)
                self.CameraSave: dict = {
                    "Mode": 2, "Distance": 2.75, "VisionCenter": Generate, "TargetRotation": Generate
                }
                self.VisionCenter: _tools.position = _tools.position(0 ,0, 1.08)
                self.TargetRotation: _tools.position = _tools.position(90, 0, 0)
            elif self.experiment_type == ExperimentType.Electromagnetism:
                self.PlSav: dict = copy.deepcopy(savTemplate.Electromagnetism)
                self.CameraSave: dict = {
                    "Mode": 0, "Distance": 3.25, "VisionCenter": Generate, "TargetRotation": Generate,
                }
                self.VisionCenter: _tools.position = _tools.position(0, 0 ,0.88)
                self.TargetRotation: _tools.position = _tools.position(90, 0, 0)
            else:
                assert False

            self.__entitle(sav_name)
        else:
            assert False

        assert isinstance(self.open_mode, OpenMode)
        assert isinstance(self._elements_position, dict)
        assert isinstance(self.Elements, list)
        assert isinstance(self.SAV_PATH, str)
        assert isinstance(self.PlSav, dict)
        assert isinstance(self.CameraSave, dict)
        assert isinstance(self.VisionCenter, _tools.position)
        assert isinstance(self.TargetRotation, _tools.position)
        assert isinstance(self.experiment_type, ExperimentType)
        if self.experiment_type == ExperimentType.Circuit:
            assert isinstance(self.Wires, set)
            assert isinstance(self.is_elementXYZ, bool)
            assert isinstance(self.elementXYZ_origin_position, _tools.position)

        _ExperimentStack.push(self)

        if self.open_mode == OpenMode.load_by_sav_name \
                or self.open_mode == OpenMode.load_by_filepath \
                or self.open_mode == OpenMode.load_by_plar_app:
            status_sav = json.loads(self.PlSav["Experiment"]["StatusSave"])

            if self.experiment_type == ExperimentType.Circuit:
                self.__load_elements(status_sav["Elements"])
                self.__load_wires(status_sav["Wires"])
            elif self.experiment_type == ExperimentType.Celestial:
                self.__load_elements(list(status_sav["Elements"].values()))
            elif self.experiment_type == ExperimentType.Electromagnetism:
                self.__load_elements(status_sav["Elements"])
            else:
                assert False

    def __load(self) -> None:
        assert isinstance(self.PlSav["Experiment"]["CameraSave"], str)
        self.CameraSave = json.loads(self.PlSav["Experiment"]["CameraSave"])
        temp = eval(f"({self.CameraSave['VisionCenter']})")
        self.VisionCenter: _tools.position = _tools.position(temp[0], temp[2], temp[1]) # x, z, y
        temp = eval(f"({self.CameraSave['TargetRotation']})")
        self.TargetRotation: _tools.position = _tools.position(temp[0], temp[2], temp[1]) # x, z, y

        if self.PlSav["Summary"] is None:
            self.PlSav["Summary"] = savTemplate.Circuit["Summary"]

        if self.PlSav["Experiment"]["Type"] == ExperimentType.Circuit.value:
            self.experiment_type = ExperimentType.Circuit
            # 该实验是否是元件坐标系
            self.is_elementXYZ: bool = False
            # 元件坐标系的坐标原点
            self.elementXYZ_origin_position: _tools.position = _tools.position(0, 0, 0)
            self.Wires: set = set() # Set[Wire] # 存档对应的导线
        elif self.PlSav["Experiment"]["Type"] == ExperimentType.Celestial.value:
            self.experiment_type = ExperimentType.Celestial
        elif self.PlSav["Experiment"]["Type"] == ExperimentType.Electromagnetism.value:
            self.experiment_type = ExperimentType.Electromagnetism
        else:
            assert False

    def __load_wires(self, _wires: list) -> None:
        assert self.experiment_type == ExperimentType.Circuit

        for wire_dict in _wires:
            self.Wires.add(
                Wire(
                    Pin(self.get_element_from_identifier(wire_dict["Source"]), wire_dict["SourcePin"]),
                    Pin(self.get_element_from_identifier(wire_dict["Target"]), wire_dict["TargetPin"]),
                    wire_dict["ColorName"][0] # e.g. "蓝"
                )
            )

    def __load_elements(self, _elements: list) -> None:
        assert isinstance(_elements, list)

        for element in _elements:
            # Unity 采用左手坐标系
            x, z, y = eval(f"({element['Position']})")

            # 实例化对象
            if self.experiment_type == ExperimentType.Circuit:
                if element["ModelID"] == "Simple Instrument":
                    from .circuit.elements.otherCircuit import Simple_Instrument
                    obj = Simple_Instrument(
                        x, y, z, elementXYZ=False,
                        instrument=int(element["Properties"].get("乐器", 0)),
                        pitch=int(element["Properties"]["音高"]),
                        velocity=element["Properties"]["音量"],
                        rated_oltage=element["Properties"]["额定电压"],
                        is_ideal_model=bool(element["Properties"]["理想模式"]),
                        is_single=bool(element["Properties"]["脉冲"])
                    )
                    for attr, val in element["Properties"].items():
                        if attr.startswith("音高"):
                            obj.add_note(int(val))
                else:
                    obj = crt_element(self, element["ModelID"], x, y, z, elementXYZ=False)
                    obj.data["Properties"] = element["Properties"]
                    obj.data["Properties"]["锁定"] = 1.0
                # 设置角度信息
                rotation = eval(f'({element["Rotation"]})')
                r_x, r_y, r_z = rotation[0], rotation[2], rotation[1]
                obj.set_rotation(r_x, r_y, r_z)
                obj.data['Identifier'] = element['Identifier']

            elif self.experiment_type == ExperimentType.Celestial:
                obj = crt_element(self, element["Model"], x, y, z)
                obj.data = element
            elif self.experiment_type == ExperimentType.Electromagnetism:
                obj = crt_element(self, element["ModelID"], x, y, z)
                obj.data = element
            else:
                assert False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # 如果无异常抛出且用户未在with语句里调用过.exit(), 则保存存档并退出实验
        if exc_type is None and _ExperimentStack.inside(self):
            self.save()
            self.exit(delete=False)

class experiment:
    def __init__(
            self,
            sav_name: str,
            read: bool = False,
            delete: bool = False,
            write: bool = True,
            elementXYZ: bool = False,
            experiment_type: ExperimentType = ExperimentType.Circuit,
            extra_filepath: Optional[str] = None,
            force_crt: bool = False,
            is_exit: bool = False,
    ) -> None:
        errors.warning("`with experiment` is deprecated, use `with Experiment` instead")
        if not isinstance(sav_name, str) or \
                not isinstance(read, bool) or \
                not isinstance(delete, bool) or \
                not isinstance(elementXYZ, bool) or \
                not isinstance(write, bool) or \
                not isinstance(experiment_type, ExperimentType) or \
                not isinstance(force_crt, bool) or \
                not isinstance(is_exit, bool) or \
                not isinstance(extra_filepath, (str, type(None))):
            raise TypeError

        self.sav_name: str = sav_name
        self.read: bool = read
        self.delete: bool = delete
        self.write: bool = write
        self.elementXYZ: bool = elementXYZ
        self.experiment_type: ExperimentType = experiment_type
        self.extra_filepath: Optional[str] = extra_filepath
        self.force_crt: bool = force_crt
        self.is_exit: bool = is_exit

    def __enter__(self) -> _Experiment:
        if self.force_crt:
            self._Experiment: _Experiment = _Experiment(
                OpenMode.crt, self.sav_name, self.experiment_type, force_crt=True
            )
        else:
            try:
                self._Experiment: _Experiment = _Experiment(OpenMode.load_by_sav_name, self.sav_name)
            except errors.ExperimentNotExistError:
                self._Experiment: _Experiment = _Experiment(OpenMode.crt, self.sav_name, self.experiment_type)

        if not self.read:
            self._Experiment.clear_elements()

        if self.elementXYZ:
            if self._Experiment.experiment_type != ExperimentType.Circuit:
                _ExperimentStack.remove(self._Experiment)
                raise errors.ExperimentTypeError
            import physicsLab.circuit.elementXYZ as _elementXYZ
            _elementXYZ.set_elementXYZ(True)

        return self._Experiment

    def __exit__(self, exc_type, exc_val, traceback) -> None:
        if exc_type is not None:
            self._Experiment.exit()
            return

        if self.is_exit:
            self._Experiment.exit()
            return
        if self.write and not self.delete:
            self._Experiment.save(extra_filepath=self.extra_filepath)
        self._Experiment.exit(delete=self.delete)
