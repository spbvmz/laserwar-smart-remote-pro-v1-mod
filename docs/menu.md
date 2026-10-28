# Меню «Девайсы» / Devices menu

[Русский](#русский) | [English](#english)

## Русский

Пункт «Девайсы» добавляется последним в главное меню пульта. Строки с числами меняются кнопками +/-, запись в устройство — по OK. Пункты-списки записывают выбранное значение сразу по OK. Пульт при этом надо направить на устройство: настройка идёт по ИК.

```
Девайсы
├─ INFO                         версия мода, автор, контакты
├─ Настройка                    (точка)
│  ├─ Сценарий                  Захват точки | Battlefield | Пункт управления
│  ├─ Задержка старта           мин:сек
│  └─ Локализация звуков        Русский | Английский
├─ Точка
│  ├─ Захват точки
│  │  ├─ Время захвата          мин:сек
│  │  ├─ Задержка отр. имп.     0..9
│  │  └─ Команда отр. импульса  63 команды
│  ├─ Точка Battlefield
│  │  ├─ Время захвата          мин:сек
│  │  ├─ Задержка отр. имп.     0..9
│  │  ├─ Команда отр. импульса  63 команды
│  │  ├─ Время удержания        мин:сек
│  │  ├─ Ускорение захвата      1..999
│  │  ├─ Команда пол. импульса  63 команды
│  │  ├─ Задержка пол. имп.     мин:сек
│  │  └─ Кол-во пол. имп.       1..30
│  └─ Пункт управления
│     ├─ Очки прочности         1..9999
│     ├─ Владелец               Нейтральный | Красные | Синие | Жёлтые | Зелёные
│     ├─ Задержка восстан.      мин:сек
│     ├─ Скорость восстан.      1..999
│     ├─ Задержка отр. имп.     0..9
│     ├─ Команда отр. импульса  63 команды
│     ├─ Команда пол. импульса  63 команды
│     ├─ Задержка пол. имп.     мин:сек
│     └─ Кол-во пол. имп.       1..30
├─ Умная аптечка 2.0
│  ├─ Кол-во комплектов         Выкл | 1..250
│  ├─ Время удержания           Выкл | 1..240
│  ├─ Попаданий на компл.       Выкл | 1..250
│  ├─ Игровой режим             Здоровье | Боезапас
│  │  └─ Энергия                Вкл режим | Команда (50) | Период 1..1800 | Активация: Нажатие / Автоматически
│  ├─ Время раунда              1 мин … 4 ч | Без ограничений
│  ├─ Команда Здоровье          28 команд
│  ├─ Команда Боезапас          8 команд
│  ├─ Команда Энергия           50 команд
│  └─ Длит. излучения           1..60
├─ Умный медик
│  ├─ Кол-во комплектов         Выкл | 1..254
│  ├─ Время срабатывания        0..240
│  ├─ Попаданий на компл.       Выкл | 1..250
│  └─ Команда                   29 команд
└─ Командный пункт
   ├─ Захват базы
   │  ├─ Сила выброса           1..100
   │  ├─ Время между выбр.      Выкл | 10..254
   │  ├─ Выстрелов для захв.    1..10000
   │  ├─ Время раунда           2 мин … 2 ч
   │  ├─ Самовосстановление     Выкл | 1..254
   │  ├─ Интервал команды       Отключено | 10 с … 10 ч
   │  └─ Команда при захвате    23 команды
   ├─ Противостояние
   │  ├─ Кол-во боезапаса       1..10000
   │  ├─ Выстрелов для уничт.   1..10000
   │  ├─ Самовосстановление     Выкл | 1..254
   │  └─ Команда                23 команды
   └─ Аптечка
      ├─ Время регенерации      Выкл | 1..254
      └─ Команда                Респаун | Старт игры | Старт с задержкой
```

Числа набираются по разрядам: «Сотни», «Десятки», «Единицы» (у больших значений ещё «Тысячи»). Для значений до 10000 разряд «Тысячи» идёт от 0 до 10.

Список ИК-команд точки (63): Здоровье, Патроны, Радиация, Аномалия, Игра, Эффекты, Команды, Пресеты, Прочее.

## English

The Devices item is added as the last item of the remote's main menu. Number rows are changed with +/- and written to the device with OK. List items are written right away on OK. Point the remote at the device: setup goes over IR.

```
Devices
├─ INFO                         mod version, author, contacts
├─ Settings                     (control point)
│  ├─ Scenario                  Point capture | Battlefield | Command post
│  ├─ Start delay               min:sec
│  └─ Sound language            Russian | English
├─ Point
│  ├─ Point capture
│  │  ├─ Capture time           min:sec
│  │  ├─ Neg. pulse delay       0..9
│  │  └─ Neg. pulse command     63 commands
│  ├─ Battlefield point
│  │  ├─ Capture time           min:sec
│  │  ├─ Neg. pulse delay       0..9
│  │  ├─ Neg. pulse command     63 commands
│  │  ├─ Hold time              min:sec
│  │  ├─ Capture boost          1..999
│  │  ├─ Pos. pulse command     63 commands
│  │  ├─ Pos. pulse delay       min:sec
│  │  └─ Pos. pulse count       1..30
│  └─ Command post
│     ├─ Hit points             1..9999
│     ├─ Owner                  Neutral | Red | Blue | Yellow | Green
│     ├─ Restore delay          min:sec
│     ├─ Restore rate           1..999
│     ├─ Neg. pulse delay       0..9
│     ├─ Neg. pulse command     63 commands
│     ├─ Pos. pulse command     63 commands
│     ├─ Pos. pulse delay       min:sec
│     └─ Pos. pulse count       1..30
├─ Smart medkit 2.0
│  ├─ Medkit sets               Off | 1..250
│  ├─ Hold time                 Off | 1..240
│  ├─ Hits per set              Off | 1..250
│  ├─ Game mode                 Health | Ammo
│  │  └─ Energy                 Enable mode | Command (50) | Period 1..1800 | Activation: Button press / Automatic
│  ├─ Round time                1 min … 4 h | Unlimited
│  ├─ Health command            28 commands
│  ├─ Ammo command              8 commands
│  ├─ Energy command            50 commands
│  └─ Emission time             1..60
├─ Smart medic
│  ├─ Medkit sets               Off | 1..254
│  ├─ Trigger time              0..240
│  ├─ Hits per set              Off | 1..250
│  └─ Command                   29 commands
└─ Command post
   ├─ Base capture
   │  ├─ Emission power         1..100
   │  ├─ Emission interval      Off | 10..254
   │  ├─ Hits to capture        1..10000
   │  ├─ Round time             2 min … 2 h
   │  ├─ Self-restore           Off | 1..254
   │  ├─ Command interval       Disabled | 10 s … 10 h
   │  └─ Capture command        23 commands
   ├─ 2x2
   │  ├─ Ammo count             1..10000
   │  ├─ Hits to destroy        1..10000
   │  ├─ Self-restore           Off | 1..254
   │  └─ Command                23 commands
   └─ Medkit
      ├─ Regen time             Off | 1..254
      └─ Command                Respawn | Start game | Delayed start
```

Numbers are entered digit by digit: Hundreds, Tens, Units (plus Thousands for larger values). For values up to 10000 the Thousands digit goes from 0 to 10.

Control point IR commands (63): Health, Ammo, Radiation, Anomaly, Game, Effects, Teams, Presets, Other.
