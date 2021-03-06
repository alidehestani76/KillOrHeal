# -*- coding: utf-8 -*-

# python imports
import random
import json
import math

# chillin imports
from chillin_server import RealtimeGameHandler
from chillin_server.gui.canvas_elements import ScaleType

# project imports
from ks.models import World, Medic, Patient, Position, Wall, PowerUp, PowerUpType
from ks.commands import Move, Turn, Fire


class GameHandler(RealtimeGameHandler):
    def on_recv_command(self, side_name, agent_name, command_type, command):
        # print('command: %s %s %s' % (side_name, command_type, command))
        if None in command.__dict__.values():
            return
        if command.name() == Fire().name():
            self.commands[(side_name, command.id)] = ((side_name, command), 1)
        else:
            self.commands[(side_name, command.id)] = ((side_name, command), 2)

    def on_initialize(self):
        print('initialize')
        self.commands = {}
        self.world = World()
        # fix sides into right list
        self.sides = list(self.sides.keys())

        world_map_file = open(self.config["map"], "r")
        self.world_map = world_map = json.loads(world_map_file.read())
        world_map_file.close()
        # set world height and width
        self.world.height, self.world.width = (world_map["height"], world_map["width"])

        # set max cycle to world for endgame
        self._max_cycle = world_map["max_cycle"]

        create_random = world_map["random_flag"]
        if create_random:
            # add medics and patients to world
            self.world.medics = {self.sides[0]: [], self.sides[1]: []}
            self.world.patients = []
            for i in range(world_map["medics"]["number"]):
                p1 = Position(self.get_random_float(2 * world_map["medics"]["radius"],
                                                    self.world.width - 2 * world_map["medics"]["radius"]),
                              float(random.randint(0, self.world.height)))
                # p1 = [Position(8.4, 16.7), Position(14.3, 9.9)][i]
                angle1 = self.get_random_float(0, 360)
                # angle1 = 45.0
                p2 = Position(self.get_random_float(2 * world_map["medics"]["radius"],
                                                    self.world.width - 2 * world_map["medics"]["radius"]),
                              float(random.randint(0, self.world.height)))
                angle2 = self.get_random_float(0, 360)
                # p2 = [Position(9.0, 18.7), Position(14.3, 9.9)][i]
                # angle2 = 90.0
                medic = self.create_medics(i, self.sides[0], p1, angle1, world_map)
                # medic.max_move_distance = self.calc_medic_max_move(medic)
                self.world.medics[self.sides[0]].append(medic)

                medic = self.create_medics(i + world_map["medics"]["number"], self.sides[1], p2, angle2, world_map)
                # medic.max_move_distance = self.calc_medic_max_move(medic)
                self.world.medics[self.sides[1]].append(medic)

            for i in range(world_map["patients"]["number"]):
                p = Position(self.get_random_float(world_map["patients"]["radius"],
                                                   self.world.width - 2 * world_map["patients"]["radius"]),
                             float(random.randint(0, self.world.height)))
                self.world.patients.append(self.create_patients(p, world_map))
                # end add medics and patients
        else:  # not random from map file!
            # add medics and patients to world
            self.world.medics = {self.sides[0]: [], self.sides[1]: []}
            self.world.patients = []
            counter1 = 0
            for direction in world_map["medics_position"][self.sides[0]]:
                p = Position(direction["x"], direction["y"])
                angle = direction["angle"]
                medic = self.create_medics(counter1, self.sides[0], p, angle, world_map)
                self.world.medics[self.sides[0]].append(medic)
                counter1 += 1
            counter2 = 0
            for direction in world_map["medics_position"][self.sides[1]]:
                p = Position(direction["x"], direction["y"])
                angle = direction["angle"]
                medic = self.create_medics(counter2, self.sides[1], p, angle, world_map)
                self.world.medics[self.sides[1]].append(medic)
                counter2 += 1
            for patient in world_map["patients_position"]:
                p = Position(patient["x"], patient["y"])
                capturable = patient["capable"]
                self.world.patients.append(self.create_patients(p, world_map, capturable))

        # set world scores and number of kills and heals
        self.world.scores = {}
        self.no_kills = {}
        self.no_heals = {}
        for side in self.sides:
            self.world.scores[side] = 0
            self.no_kills[side] = 0
            self.no_heals[side] = 0
        # end set world scores and number of kills and heals

        # set walls into world
        self.walls_line_equation = []  # ax + by + c = 0
        self.world.walls = []
        for wall in world_map["walls"]:
            start_pos = Position(wall[0]["x"], wall[0]["y"])
            end_pos = Position(wall[1]["x"], wall[1]["y"])
            self.world.walls.append(Wall(start_pos, end_pos))
            line_equation = (end_pos.y - start_pos.y, start_pos.x - end_pos.x,
                             ((start_pos.y - end_pos.y) * start_pos.x) + ((end_pos.x - start_pos.x) * start_pos.y))
            self.walls_line_equation.append(line_equation)

        # end set walls into world

        # confidant of map bound
        for wall in self.confidence_of_map_bound():
            start_pos = Position(wall[0]["x"], wall[0]["y"])
            end_pos = Position(wall[1]["x"], wall[1]["y"])
            self.world.walls.append(Wall(start_pos, end_pos))
            line_equation = (end_pos.y - start_pos.y, start_pos.x - end_pos.x,
                             ((start_pos.y - end_pos.y) * start_pos.x) + ((end_pos.x - start_pos.x) * start_pos.y))
            self.walls_line_equation.append(line_equation)
        # end on confidence of map bound

        # set powerups positions
        self.power_ups = []
        self.world.powerups = []
        for powerup in self.world_map["powerups"]["positions"]:
            self.power_ups.append([Position(powerup["x"], powerup["y"]), 0])
        # end set powerups

        # list for medics should be deleted after laser
        self.down_medics = []

        # list of patients should be deleted after they healed
        self.down_patients = []

    def on_initialize_gui(self):
        print('initialize gui')
        self.gui_config = gui_config = self.config["gui"]
        # set coefficient of gui height and width
        width_coefficient = self.world_map["monitor_width"] / self.world.width
        height_coefficient = self.world_map["monitor_height"] / self.world.height

        self.canvas.create_image("Background", 0, 0, scale_type=ScaleType.ScaleX,
                                 scale_value=int(self.canvas.width * 100.0 / self.config["gui"]["background_size"][0]),
                                 custom_ref="bckgrnd")
        self.canvas.edit_image("bckgrnd", scale_type=ScaleType.ScaleY,
                               scale_value=int(self.canvas.height * 100.0 / self.config["gui"]["background_size"][1]))
        self.medics_ref = {}
        self.medics_info_ref = {}
        for side in self.world.medics:
            for medic in self.world.medics[side]:
                index = self.sides.index(side)
                x = int(medic.position.x * width_coefficient)
                y = int(medic.position.y * height_coefficient)
                # print medic.position.x, medic.position.y
                rx = int(2 * medic.radius * width_coefficient)
                ry = int(2 * medic.radius * height_coefficient)
                # print "medics", x, y, rx, ry
                self.medics_ref[(side, medic.id)] = ref = self.canvas.create_image(self.sides[index], x, y,
                                                                                   scale_type=ScaleType.ScaleToWidth,
                                                                                   scale_value=rx,
                                                                                   angle=medic.angle,
                                                                                   center_origin=True)
                x += 12
                y += -45
                refs = []
                mid = str(medic.id)
                text_color = self.canvas.make_rgba(12, 12, 12, 255)
                refs.append(self.canvas.create_text(mid, x, y, text_color, 22))
                x1 = x - 12 - int(medic.radius * width_coefficient)
                y1 = y + 45 + int(medic.radius * width_coefficient)
                x2 = x1 + int(medic.health * (2 * medic.radius * width_coefficient / medic.max_health))
                y2 = y1
                color = self.canvas.make_rgba(56, 188, 72, 255)
                refs.append(self.canvas.create_line(x1, y1, x2, y2, color, 4))
                x1 = x1
                y1 += 4
                x2 = x1 + int(medic.laser_count * (2 * medic.radius * width_coefficient / medic.laser_max_count))
                y2 = y1
                color = self.canvas.make_rgba(223, 96, 2, 255)
                refs.append(self.canvas.create_line(x1, y1, x2, y2, color, 4))
                x1 = x1
                y1 += 4
                x2 = x1 + int(medic.time_to_reload * (2 * medic.radius * width_coefficient / medic.reload_time))
                y2 = y1
                color = self.canvas.make_rgba(26, 15, 240, 255)
                refs.append(self.canvas.create_line(x1, y1, x2, y2, color, 4))
                self.medics_info_ref[(side, medic.id)] = refs

        self.patients_ref = []
        self.modifying_patients_and_medics = []  # tuple(patient_index, new Medic if exists)
        for patient in self.world.patients:
            x = int(patient.position.x * width_coefficient)
            y = int(patient.position.y * height_coefficient)
            rx = int(2 * patient.radius * width_coefficient)
            ry = int(2 * patient.radius * height_coefficient)
            # print "patient", x, y, rx, ry
            if patient.capturable:
                self.patients_ref.append(self.canvas.create_image("CapturablePatient", x, y, scale_type=ScaleType.ScaleToWidth,
                                                                  scale_value=rx,
                                                                  center_origin=True))
            else:
                self.patients_ref.append(self.canvas.create_image("Patient", x, y, scale_type=ScaleType.ScaleToWidth,
                                                                  scale_value=rx,
                                                                  center_origin=True))

        for wall in self.world.walls:
            x1 = int(wall.start_pos.x * width_coefficient)
            y1 = int(wall.start_pos.y * height_coefficient)
            x2 = int(wall.end_pos.x * width_coefficient)
            y2 = int(wall.end_pos.y * height_coefficient)
            wall_color = self.canvas.make_rgba(12, 12, 12, 255)
            self.canvas.create_line(x1, y1, x2, y2, wall_color)

        # set cycle counter on gui
        x = 1130
        y = 36
        color = self.canvas.make_rgba(0, 40, 10, 255)
        self.cycle_ref = self.canvas.create_text("Cycle:  " + str(self.current_cycle), x, y, color, 32,
                                                 center_origin=True)

        # set score board on gui
        sides_color = {self.sides[0]: self.canvas.make_rgba(213, 211, 3, 255),
                       self.sides[1]: self.canvas.make_rgba(150, 115, 70, 255)}

        self.canvas.create_image(self.sides[0], 1040, 200, scale_type=ScaleType.ScaleToWidth,
                                 scale_value=80, angle=270, center_origin=True)
        self.canvas.create_image(self.sides[1], 1220, 200, scale_type=ScaleType.ScaleToWidth,
                                 scale_value=80, angle=270, center_origin=True)

        self.canvas.create_text(self.sides[0] + " Vs. " + self.sides[1], 1130, 285, color, 29, center_origin=True)
        self.scores_ref = self.canvas.create_text(str(self.world.scores[self.sides[0]]) + "   :score:   " +
                                                  str(self.world.scores[self.sides[1]]),
                                                  1130, 330, color, 40, center_origin=True)

        self.kills_ref = self.canvas.create_text(str(self.no_kills[self.sides[0]]) + "  :kills:  " +
                                                 str(self.no_kills[self.sides[1]]),
                                                 1130, 375, color, 40, center_origin=True)
        self.heals_ref = self.canvas.create_text(str(self.no_heals[self.sides[0]]) + "  :heals:  " +
                                                 str(self.no_heals[self.sides[1]]),
                                                 1130, 415, color, 40, center_origin=True)


        self.power_ups_ref = {}  # key = (x, y)
        self.modifying_power_ups = []  # [bool create or delete, id]

        self.delete_fire_ref = []
        self.create_fire_ref = []

        self.down_medics_ref = []
        self.canvas.apply_actions()

    def on_process_cycle(self):
        print('process: %s' % self.current_cycle)
        fire_cmds = [c[0] for c in self.commands.values() if c[1] == 1]
        other_cmds = [c[0] for c in self.commands.values() if c[1] == 2]
        for side, command in fire_cmds:
            for medic in self.world.medics[side]:
                if medic.id == command.id:
                    self._handle_command(side, medic, command)
        # should damaged medics be removed
        for medic in self.down_medics:
            if medic in self.world.medics[medic.side_name]:
                self.world.medics[medic.side_name].remove(medic)
                self.world.patients.append(self.create_patients(Position(medic.position.x, medic.position.y),
                                                                self.world_map, True))
        self.down_medics = []

        for side, command in other_cmds:
            for medic in self.world.medics[side]:
                if medic.id == command.id:
                    self._handle_command(side, medic, command)

        for side in self.world.medics:
            for medic in self.world.medics[side]:
                self._healing(side, medic)
                self._crush_powerup_and_medic(medic)

        self._create_power_ups_randomly()
        self._remove_powerups_end_time()
        self._reload_laser_count()
        # empty commands dict
        self.commands = {}

        if self.current_cycle >= self._max_cycle:
            end_game_status = self.win_or_draw()
            details = {"scores": {self.sides[0]: str(self.world.scores[self.sides[0]]),
                                  self.sides[1]: str(self.world.scores[self.sides[1]])},

                       "kills ": {self.sides[0]: str(self.no_kills[self.sides[0]]),
                                  self.sides[1]: str(self.no_kills[self.sides[1]])},

                       "heals ": {self.sides[0]: str(self.no_heals[self.sides[0]]),
                                  self.sides[1]: str(self.no_heals[self.sides[1]])}}

            if end_game_status[0] == 1:  # draw
                self.end_game(details=details)
            else:
                self.end_game(end_game_status[1], details=details)

        else:
            end_game_status = False
            details = {"scores": {self.sides[0]: str(self.world.scores[self.sides[0]]),
                                  self.sides[1]: str(self.world.scores[self.sides[1]])},

                       "kills ": {self.sides[0]: str(self.no_kills[self.sides[0]]),
                                  self.sides[1]: str(self.no_kills[self.sides[1]])},

                       "heals ": {self.sides[0]: str(self.no_heals[self.sides[0]]),
                                  self.sides[1]: str(self.no_heals[self.sides[1]])}}
            for side in self.world.medics:
                if len(self.world.medics[side]) == 0:
                    end_game_status = self.win_or_draw()
                    break

            if end_game_status:
                if end_game_status[0] == 1:  # draw
                    self.end_game(details=details)
                else:
                    self.end_game(end_game_status[1], details=details)

    def on_update_clients(self):
        print('update clients')
        confident_walls = self.world.walls[-4:]
        self.world.walls = self.world.walls[:-4]
        self.send_snapshot(self.world)
        self.world.walls += confident_walls

    def on_update_gui(self):
        print('update gui')
        width_coefficient = self.world_map["monitor_width"] / self.world.width
        height_coefficient = self.world_map["monitor_height"] / self.world.height
        # update medics positions
        for side in self.world.medics:
            for medic in self.world.medics[side]:
                x = int(medic.position.x * width_coefficient)
                y = int(medic.position.y * height_coefficient)
                tmp = self.medics_ref.get((side, medic.id), None)
                tmp2 = self.medics_info_ref.get((side, medic.id), None)
                if tmp is not None:
                    self.canvas.edit_image(self.medics_ref[side, medic.id], x, y, angle=medic.angle)
                    if tmp2 is not None:
                        id_ref, health_ref, laser_ref, reload_ref = self.medics_info_ref[(side, medic.id)]
                        x += 12
                        y += -45
                        self.canvas.edit_text(id_ref, str(medic.id),x, y)
                        x1 = x - 12 - int(medic.radius * width_coefficient)
                        y1 = y + 45 + int(medic.radius * width_coefficient)
                        x2 = x1 + int(medic.health * (2 * medic.radius * width_coefficient / medic.max_health))
                        y2 = y1
                        self.canvas.edit_line(health_ref, x1, y1, x2, y2)
                        x1 = x1
                        y1 += 4
                        x2 = x1 + int(medic.laser_count * (2 * medic.radius * width_coefficient / medic.laser_max_count))
                        y2 = y1
                        self.canvas.edit_line(laser_ref, x1, y1, x2, y2)
                        x1 = x1
                        y1 += 4
                        x2 = x1 + int(medic.time_to_reload * (2 * medic.radius * width_coefficient / medic.reload_time))
                        y2 = y1
                        self.canvas.edit_line(reload_ref, x1, y1, x2, y2)

                else:
                    continue

        # end update medics positions

        # delete medics whose health is 0
        for medic in self.down_medics_ref:
            ref = self.medics_ref.get((medic.side_name, medic.id), None)
            info_refs = self.medics_info_ref.get((medic.side_name, medic.id), None)
            if ref is not None:
                self.canvas.delete_element(ref)
                if info_refs is not None:
                    for i in info_refs:
                        self.canvas.delete_element(i)
                x = int(medic.position.x * width_coefficient)
                y = int(medic.position.y * height_coefficient)
                rx = int(self.world_map["patients"]["radius"] * width_coefficient)
                ry = int(medic.radius * height_coefficient)
                # print "patient", x, y, rx, ry
                self.patients_ref.append(self.canvas.create_image("CapturablePatient", x, y,
                                                                  scale_type=ScaleType.ScaleToWidth,
                                                                  scale_value=rx,
                                                                  center_origin=True))
        self.down_medics_ref = []
        # end delete medics whose health is 0

        # update patients if remove and create new medics if needed
        for item in self.modifying_patients_and_medics:
            if item[0] < len(self.patients_ref):
                self.canvas.delete_element(self.patients_ref[item[0]])
                self.patients_ref.remove(self.patients_ref[item[0]])
            if item[1] != -1:
                medic = item[1]
                x = int(medic.position.x * width_coefficient)
                y = int(medic.position.y * height_coefficient)
                rx = int(2 * medic.radius * width_coefficient)
                self.medics_ref[(medic.side_name, medic.id)] = self.canvas.create_image(medic.side_name, x, y,
                                                                                        scale_type=ScaleType.ScaleToWidth,
                                                                                        scale_value=rx,
                                                                                        angle=medic.angle,
                                                                                        center_origin=True)
                x += 12
                y += -45
                refs = []
                mid = str(medic.id)
                text_color = self.canvas.make_rgba(12, 12, 12, 255)
                refs.append(self.canvas.create_text(mid, x, y, text_color, 22))
                x1 = x - 12 - int(medic.radius * width_coefficient)
                y1 = y + 45 + int(medic.radius * width_coefficient)
                x2 = x1 + int(medic.health * (2 * medic.radius * width_coefficient / medic.max_health))
                y2 = y1
                color = self.canvas.make_rgba(56, 188, 72, 255)
                refs.append(self.canvas.create_line(x1, y1, x2, y2, color, 4))
                x1 = x1
                y1 += 4
                x2 = x1 + int(medic.laser_count * (2 * medic.radius * width_coefficient / medic.laser_max_count))
                y2 = y1
                color = self.canvas.make_rgba(223, 96, 2, 255)
                refs.append(self.canvas.create_line(x1, y1, x2, y2, color, 4))
                x1 = x1
                y1 += 4
                x2 = x1 + int(medic.time_to_reload * (2 * medic.radius * width_coefficient / medic.reload_time))
                y2 = y1
                color = self.canvas.make_rgba(26, 15, 240, 255)
                refs.append(self.canvas.create_line(x1, y1, x2, y2, color, 4))
                self.medics_info_ref[(medic.side_name, medic.id)] = refs

        self.modifying_patients_and_medics = []  # should be empty after everything done
        # end update patients if remove and create new medics if needed

        # update powerups
        for powerup in self.modifying_power_ups:
            pup = powerup[1]
            if powerup[0] == 0:  # delete
                ref = self.power_ups_ref.pop((pup.position.x, pup.position.y))
                self.canvas.delete_element(ref)
            else:  # create
                if PowerUpType.LASER == pup.type:
                    img = "Laser"
                else:
                    img = "Healpack"
                x = int(pup.position.x * width_coefficient)
                y = int(pup.position.y * height_coefficient)
                rx = int(2 * 0.5 * width_coefficient)
                ref = self.canvas.create_image(img, x, y, scale_type=ScaleType.ScaleToWidth, scale_value=rx,
                                               center_origin=True)
                self.power_ups_ref[(pup.position.x, pup.position.y)] = ref

        self.modifying_power_ups = []
        # end update powerups

        # draw fire and remove
        for i in self.delete_fire_ref:
            self.canvas.delete_element(i)
        self.delete_fire_ref = []

        for i in self.create_fire_ref:
            x1 = int(i[0] * width_coefficient)
            y1 = int(i[1] * height_coefficient)
            x2 = int(i[2] * width_coefficient)
            y2 = int(i[3] * height_coefficient)
            wall_color = self.canvas.make_rgba(203, 96, 1, 255)
            ref = self.canvas.create_line(x1, y1, x2, y2, wall_color, 3)
            self.delete_fire_ref.append(ref)
        self.create_fire_ref = []
        # end draw fire and remove

        # update cycle
        self.canvas.edit_text(self.cycle_ref, "Cycle:   " + str(self.current_cycle))

        # update score board
        self.canvas.edit_text(self.scores_ref, str(self.world.scores[self.sides[0]]) + "  :score:  " +
                              str(self.world.scores[self.sides[1]]))
        self.canvas.edit_text(self.kills_ref, str(self.no_kills[self.sides[0]]) + "  :kills:  " +
                              str(self.no_kills[self.sides[1]]))
        self.canvas.edit_text(self.heals_ref, str(self.no_heals[self.sides[0]]) + "  :heals:  " +
                              str(self.no_heals[self.sides[1]]))

        self.canvas.apply_actions()

    @staticmethod
    def get_random_float(start, end):
        return random.uniform(start, end)

    @staticmethod
    def create_medics(mid, side_name, position, angle, world_map, laser_count=None):
        return Medic(mid,
                     side_name,
                     position,
                     world_map["medics"]["radius"],
                     world_map["medics"]['max_move_distance'],
                     angle,
                     world_map["medics"]['max_turn_angle'],
                     world_map["medics"]["max_fire_angle"],
                     world_map["medics"]['health'],
                     world_map["medics"]['max_health'],
                     world_map["medics"]["laser_count"] if laser_count is None else 0,
                     world_map["medics"]["laser_damage"],
                     world_map["medics"]["laser_range"],
                     world_map["medics"]["laser_max_count"],
                     world_map["medics"]["healing_remaining_time"],
                     world_map["medics"]["time_to_reload"],
                     world_map["medics"]["reload_time"],
                     world_map["medics"]["death_score"])

    @staticmethod
    def create_patients(position, world_map, capturable=None):
        if capturable is not None:
            return Patient(position,
                           world_map["patients"]["radius"],
                           world_map["patients"]["healing_duration"],
                           capturable,
                           world_map["patients"]["heal_score_capturable" if capturable else "heal_score"])
        return Patient(position,
                       world_map["patients"]["radius"],
                       world_map["patients"]["healing_duration"],
                       False,
                       world_map["patients"]["heal_score"])

    def _handle_command(self, side, medic, cmd):
        handlers = {
            Move.name(): self._handle_move,
            Turn.name(): self._handle_turn,
            Fire.name(): self._handle_fire
        }
        handlers[cmd.name()](side, medic, cmd)

    def _healing(self, side, medic):

        for i in range(len(self.world.patients)):
            patient = self.world.patients[i]
            patient_medic_dist = self.get_2_points_distance(medic.position.x, medic.position.y,
                                                            patient.position.x, patient.position.y)
            if patient_medic_dist <= patient.radius + medic.radius:
                if medic.healing_remaining_time == 0:
                    medic.healing_remaining_time = patient.healing_duration
                    break  # not to check other patients
                else:
                    medic.healing_remaining_time -= 1
                    if medic.healing_remaining_time == 0:
                        if patient.capturable:
                            if self.world.medics:
                                mid = sorted(self.world.medics[side], key=lambda x: x.id)[-1].id
                                mid += 1
                            else:
                                mid = 1
                            medic_temp = self.create_medics(mid, side, patient.position, medic.angle
                                                            , self.world_map)
                            self.world.medics[side].append(medic_temp)
                            self.world.scores[side] += patient.heal_score
                            self.no_heals[side] += 1
                            self.world.patients.remove(patient)
                            self.modifying_patients_and_medics.append((i, medic_temp))

                        else:
                            self.world.scores[side] += patient.heal_score
                            self.no_heals[side] += 1
                            self.world.patients.remove(patient)
                            self.modifying_patients_and_medics.append((i, -1))

                        break  # not to check other patients
                    break # not to check other patients
            else:
                continue

    def _handle_move(self, side, medic, cmd):
        dist = cmd.distance
        if abs(dist) > medic.max_move_distance:
            dist = medic.max_move_distance if dist > 0 else - medic.max_move_distance

        if abs(dist) <= medic.max_move_distance:
            medic.healing_remaining_time = 0
            x = medic.position.x + dist * math.cos(math.radians(medic.angle))
            y = medic.position.y - dist * math.sin(math.radians(medic.angle))
            res = self.check_medic_crush_the_wall(medic, x, y)
            if res:
                pass
            else:
                medic.position.x = x
                medic.position.y = y

    def calc_medic_max_move(self, medic):
        pass

    def check_medic_crush_the_wall(self, medic, x, y):
        result = []
        for i in range(len(self.world.walls)):
            wall_line_eq = self.walls_line_equation[i]
            wall = self.world.walls[i]
            a, b, c = wall_line_eq
            if abs(((a * x) + (b * y) + c) / (a**2 + b**2)**0.5) < 0.001:
                a1 = -b
                b1 = a
                c1 = (-1.0 * a * wall.start_pos.y) + (b * wall.start_pos.x)
                a2 = -b
                b2 = a
                c2 = (-1.0 * a * wall.end_pos.y) + (b * wall.end_pos.x)
                r1 = abs(((a1 * x) + (b1 * y) + c1) / (a1 ** 2 + b1 ** 2) ** 0.5)
                r2 = abs(((a2 * x) + (b2 * y) + c2) / (a2 ** 2 + b2 ** 2) ** 0.5)
                if r1 < medic.radius:
                    result.append((i, r1 - medic.radius))
                    break
                elif r2 < medic.radius:
                    result.append((i, r2 - medic.radius))
                    break
                elif abs(((a * x) + (b * y) + c) / (a ** 2 + b ** 2) ** 0.5) < medic.radius:
                    if self.has_line_and_circle_meet_point(wall.start_pos.x, wall.start_pos.y,
                                                           wall.end_pos.x, wall.end_pos.y, wall_line_eq,
                                                           x, y, medic.radius):
                        result.append(i)
                        break
                else:
                    continue
            elif abs(((a * x) + (b * y) + c) / (a ** 2 + b ** 2) ** 0.5) < medic.radius \
                    and (wall.start_pos.x < x < wall.end_pos.x
                         or wall.start_pos.y < y < wall.end_pos.y):
                result.append(i)
                break
            elif abs(((a * x) + (b * y) + c) / (a ** 2 + b ** 2) ** 0.5) < medic.radius:
                if self.has_line_and_circle_meet_point(wall.start_pos.x, wall.start_pos.y,
                                                       wall.end_pos.x, wall.end_pos.y, wall_line_eq,
                                                       x, y, medic.radius):
                    result.append(i)
                    break
            else:
                continue

        return result if result else False

    def _handle_turn(self, side, medic, cmd):
        clockwise = cmd.clockwise
        angle = cmd.angle
        if abs(angle) > self.world_map["medics"]["max_turn_angle"]:
            angle = self.world_map["medics"]["max_turn_angle"] if angle > 0 else - self.world_map["medics"]["max_turn_angle"]

        if abs(angle) <= self.world_map["medics"]["max_turn_angle"]:
            medic.healing_remaining_time = 0
            if clockwise:
                medic.angle -= angle
                medic.angle %= 360
            else:
                medic.angle += angle
                medic.angle %= 360

    def _handle_fire(self, side, medic, cmd):
        fire_angle = cmd.angle
        clock_wise = cmd.clockwise
        angle = medic.angle
        if abs(fire_angle) > self.world_map["medics"]["max_fire_angle"]:
            fire_angle = self.world_map["medics"]["max_fire_angle"] if fire_angle > 0 else - self.world_map["medics"]["max_fire_angle"]

        if abs(fire_angle) <= self.world_map["medics"]["max_fire_angle"]:
            if clock_wise:
                angle -= fire_angle
            else:
                angle += fire_angle
            angle %= 360
            if medic.laser_count != 0:
                medic.healing_remaining_time = 0
                medic.laser_count -= 1
                x2, y2, line_eq = self.check_fire_crush_the_wall(medic.position.x, medic.position.y, angle)
                x1, y1 = medic.position.x, medic.position.y

                x2, y2, o_medic = self.check_fire_crush_the_medics(x1, y1, x2, y2, line_eq, medic)

                if o_medic:
                    o_medic.health -= medic.laser_damage
                    if o_medic.health <= 0:
                        self.down_medics.append(o_medic)
                        self.down_medics_ref.append(o_medic)
                        self.world.scores[side] += o_medic.death_score
                        self.no_kills[side] += 1

                self.create_fire_ref.append([x2, y2, x1, y1])

    def _create_power_ups_randomly(self):
        chance = random.randint(0, 100)
        if chance <= self.world_map["powerups"]["chance"] and len(self.power_ups) >= 2:
            chance = random.randint(0, len(self.power_ups) - 1)
            if self.power_ups[chance][1] == 0:
                self.power_ups[chance][1] = 1

                power_up_type = random.choice([(PowerUpType.LASER, 0),
                                               (PowerUpType.HEAL_PACK, self.world_map["healpack"]["max_healing"])])
                pup = PowerUp(power_up_type[0], self.power_ups[chance][0],
                              self.world_map["powerups"]["appearance_time"], power_up_type[1])
                self.world.powerups.append(pup)
                self.modifying_power_ups.append([1, pup])
                self.power_ups.remove(self.power_ups[chance])

    def _remove_powerups_end_time(self):
        result = []
        for i in range(len(self.world.powerups)):
            pup = self.world.powerups[i]
            if pup.appearance_time == 0:
                result.append(i)
                self.modifying_power_ups.append([0, pup])
                if pup.type == PowerUpType.LASER:
                    t = 0
                else:
                    t = 1

                self.power_ups.append([pup.position, t, 0])
            else:
                pup.appearance_time -= 1
        for i in result:
            self.world.powerups.pop(i)

    def _crush_powerup_and_medic(self, medic):
        result = []
        for i in range(len(self.world.powerups)):
            pup = self.world.powerups[i]
            dist = self.get_2_points_distance(medic.position.x, medic.position.y, pup.position.x, pup.position.y)

            if dist <= 0.5 + medic.radius:
                if pup.type == PowerUpType.LASER:
                    if medic.laser_count == medic.laser_max_count:
                        continue
                    else:
                        medic.laser_count += 1
                        result.append(i)
                        self.modifying_power_ups.append([0, pup])
                        self.power_ups.append([pup.position, 0, 0])
                else:
                    if medic.health == medic.max_health:
                        continue
                    else:
                        medic.health += pup.value
                        medic.health = medic.max_health if medic.health > medic.max_health else medic.health
                        result.append(i)
                        self.modifying_power_ups.append([0, pup])
                        self.power_ups.append([pup.position, 1, 0])
            else:
                continue
        for i in result:
            self.world.powerups.pop(i)

    def check_fire_crush_the_wall(self, x, y, angle):
        # consider 3 lines equation
        result = []
        x_max = x + self.world_map["medics"]["laser_range"] * math.cos(math.radians(angle))
        y_max = y - self.world_map["medics"]["laser_range"] * math.sin(math.radians(angle))
        fire_line_eq = ((y - y_max), (x_max - x), ((y * (x - x_max)) + (x * (y_max - y))))
        for i in range(len(self.world.walls)):
            wall = self.world.walls[i]
            v1 = (wall.start_pos.x - x, wall.start_pos.y - y)
            size_v1 = (v1[0] ** 2 + v1[1]**2)**0.5
            v2 = (wall.end_pos.x - x, wall.end_pos.y - y)
            size_v2 = (v2[0] ** 2 + v2[1]**2)**0.5
            theta = math.degrees(math.acos((v1[0] * v2[0] + v1[1] * v2[1]) / (size_v1 * size_v2)))
            vl = (x_max - x, y_max - y)
            size_vl = (vl[0] ** 2 + vl[1]**2)**0.5
            theta1 = math.degrees(math.acos((v1[0] * vl[0] + v1[1] * vl[1]) / (size_v1 * size_vl)))
            theta2 = math.degrees(math.acos((vl[0] * v2[0] + vl[1] * v2[1]) / (size_vl * size_v2)))
            if abs(theta - theta1 - theta2) < 0.01:
                a, b, c = self.walls_line_equation[i]
                h = ((a * x) + (b * y) + c) / (a**2 + b**2)**0.5
                if h != 0:
                    x2 = x + self.world_map["medics"]["laser_range"] * math.cos(math.radians(angle))
                    y2 = y - self.world_map["medics"]["laser_range"] * math.sin(math.radians(angle))
                    fire_line_eq = ((y - y2), (x2 - x), ((y * (x - x2)) + (x * (y2 - y))))
                    a, b = self.get_lines_meet_point(fire_line_eq, self.walls_line_equation[i])
                    if ((x-a)**2 + (y - b)**2)**0.5 <= ((x-x_max)**2 + (y - y_max)**2)**0.5:
                        x_max, y_max = a, b
                    result.append(self.get_lines_meet_point(fire_line_eq, self.walls_line_equation[i]))
        return x_max, y_max, fire_line_eq

    def check_fire_crush_the_medics(self, x_src, y_src, x_dst, y_dst, line_eq, medic):
        res_medic = None
        for side in self.world.medics:
            if side != medic.side_name:
                for i in range(len(self.world.medics[side])):
                    a, b, c = line_eq
                    o_medic = self.world.medics[side][i]
                    r = o_medic.radius
                    dist = (o_medic.position.x * a + o_medic.position.y * b + c) / (a**2 + b**2)**0.5
                    if dist <= o_medic.radius:
                        x_tmp, y_tmp, x1_tmp, y1_tmp, x2_tmp, y2_tmp, = [None for _ in range(6)]
                        if a == 0:
                            y_tmp = -c / b
                            delta = (-2 * o_medic.position.x)**2 - 4 * (o_medic.position.x ** 2 + (y_tmp - o_medic.position.y)**2 - o_medic.radius**2)
                            if delta > 0:
                                x1_tmp = ((2 * o_medic.position.x) + delta**0.5) / 2.0
                                x2_tmp = ((2 * o_medic.position.x) - delta**0.5) / 2.0
                            elif delta == 0:
                                x_tmp = o_medic.position.x
                            else:
                                continue
                        elif b == 0:
                            x_tmp = -c / a
                            delta = (-2 * o_medic.position.y)**2 - 4 * (o_medic.position.y ** 2 + (x_tmp - o_medic.position.x)**2 - o_medic.radius**2)
                            if delta > 0:
                                y1_tmp = ((2 * o_medic.position.y) + delta**0.5) / 2.0
                                y2_tmp = ((2 * o_medic.position.y) - delta**0.5) / 2.0
                            elif delta == 0:
                                y_tmp = o_medic.position.y
                            else:
                                continue
                        else:
                            delta = (-2 * a**2 * o_medic.position.y + 2 * a * b * o_medic.position.x + 2 * b * c)**2 - 4 * (a**2 + b **2) * (a**2 * o_medic.position.x**2 + a**2 * o_medic.position.y**2 + 2 * a * c * o_medic.position.x + c**2 - a**2 * r**2)
                            if delta > 0:
                                y1_tmp = (-(-2 * a**2 * o_medic.position.y + 2 * a * b * o_medic.position.x + 2 * b * c) + delta**0.5) / (2 * (a**2 + b**2))
                                y2_tmp = (-(-2 * a**2 * o_medic.position.y + 2 * a * b * o_medic.position.x + 2 * b * c) - delta**0.5) / (2 * (a**2 + b**2))
                                x1_tmp = (-c - b * y1_tmp) / a
                                x2_tmp = (-c - b * y2_tmp) / a
                            elif delta == 0:
                                y_tmp = (-(-2 * a**2 * o_medic.position.y + 2 * a * b * o_medic.position.x + 2 * b * c)) / (2 * (a**2 + b**2))
                                x_tmp = (-c - b * y_tmp) / a

                            else:
                                continue
                        if x2_tmp is not None and y2_tmp is not None:
                            vl = (x_dst - x_src, y_dst - y_src)
                            vm1 = (x1_tmp - x_src, y1_tmp - y_src)
                            vm2 = (x2_tmp - x_src, y2_tmp - y_src)

                            if vl[0]*vm1[0] + vl[1]*vm1[1] > 0:
                                if vl[0]*vm2[0] + vl[1]*vm2[1] > 0:
                                    d = (vl[0]**2 + vl[1]**2)**0.5
                                    d1 = (vm1[0]**2 + vm1[1]**2)**0.5
                                    d2 = (vm2[0]**2 + vm2[1]**2)**0.5
                                    if d1 <= d2 and d1 <= d:
                                        x_dst, y_dst = x1_tmp, y1_tmp
                                        res_medic = o_medic
                                    elif d2 <= d1 and d2 < d:
                                        x_dst, y_dst = x2_tmp, y2_tmp
                                        res_medic = o_medic
                                else:
                                    d = (vl[0]**2 + vl[1]**2)**0.5
                                    d1 = (vm1[0]**2 + vm1[1]**2)**0.5
                                    if d1 <= d:
                                        x_dst, y_dst = x1_tmp, y1_tmp
                                        res_medic = o_medic
                            else:
                                if vl[0]*vm2[0] + vl[1]*vm2[1] > 0:
                                    d = (vl[0]**2 + vl[1]**2)**0.5
                                    d2 = (vm2[0]**2 + vm2[1]**2)**0.5
                                    if d2 <= d:
                                        x_dst, y_dst = x2_tmp, y2_tmp
                                        res_medic = o_medic
                        elif x2_tmp is not None and y_tmp is not None:
                            vl = (x_dst - x_src, y_dst - y_src)
                            vm1 = (x1_tmp - x_src, y_tmp - y_src)
                            vm2 = (x2_tmp - x_src, y_tmp - y_src)
                            if vl[0]*vm1[0] + vl[1]*vm1[1] > 0:
                                if vl[0]*vm2[0] + vl[1]*vm2[1] > 0:
                                    d = (vl[0]**2 + vl[1]**2)**0.5
                                    d1 = (vm1[0]**2 + vm1[1]**2)**0.5
                                    d2 = (vm2[0]**2 + vm2[1]**2)**0.5
                                    if d1 <= d2 and d1 <= d:
                                        x_dst, y_dst = x1_tmp, y_tmp
                                        res_medic = o_medic
                                    elif d2 <= d1 and d2 < d:
                                        x_dst, y_dst = x2_tmp, y_tmp
                                        res_medic = o_medic
                                else:
                                    d = (vl[0]**2 + vl[1]**2)**0.5
                                    d1 = (vm1[0]**2 + vm1[1]**2)**0.5
                                    if d1 <= d:
                                        x_dst, y_dst = x1_tmp, y_tmp
                                        res_medic = o_medic
                            else:
                                if vl[0]*vm2[0] + vl[1]*vm2[1] > 0:
                                    d = (vl[0]**2 + vl[1]**2)**0.5
                                    d2 = (vm2[0]**2 + vm2[1]**2)**0.5
                                    if d2 <= d:
                                        x_dst, y_dst = x2_tmp, y_tmp
                                        res_medic = o_medic

                        elif y2_tmp is not None and x_tmp is not None:
                            vl = (x_dst - x_src, y_dst - y_src)
                            vm1 = (x_tmp - x_src, y1_tmp - y_src)
                            vm2 = (x_tmp - x_src, y2_tmp - y_src)
                            if vl[0]*vm1[0] + vl[1]*vm1[1] > 0:
                                if vl[0]*vm2[0] + vl[1]*vm2[1] > 0:
                                    d = (vl[0]**2 + vl[1]**2)**0.5
                                    d1 = (vm1[0]**2 + vm1[1]**2)**0.5
                                    d2 = (vm2[0]**2 + vm2[1]**2)**0.5
                                    if d1 <= d2 and d1 <= d:
                                        x_dst, y_dst = x_tmp, y1_tmp
                                        res_medic = o_medic
                                    elif d2 <= d1 and d2 < d:
                                        x_dst, y_dst = x_tmp, y2_tmp
                                        res_medic = o_medic
                                else:
                                    d = (vl[0]**2 + vl[1]**2)**0.5
                                    d1 = (vm1[0]**2 + vm1[1]**2)**0.5
                                    if d1 <= d:
                                        x_dst, y_dst = x_tmp, y1_tmp
                                        res_medic = o_medic
                            else:
                                if vl[0]*vm2[0] + vl[1]*vm2[1] > 0:
                                    d = (vl[0]**2 + vl[1]**2)**0.5
                                    d2 = (vm2[0]**2 + vm2[1]**2)**0.5
                                    if d2 <= d:
                                        x_dst, y_dst = x_tmp, y2_tmp
                                        res_medic = o_medic
                        elif x_tmp is not None and y_tmp is not None:
                            vl = (x_dst - x_src, y_dst - y_src)
                            vm = (x_tmp - x_src, y_tmp - y_src)
                            if vl[0]*vm[0] + vl[1]*vm[1] > 0:
                                d = (vl[0]**2 + vl[1]**2)**0.5
                                d1 = (vm[0]**2 + vm[1]**2)**0.5
                                if d1 <= d:
                                    x_dst, y_dst = x_tmp, y_tmp
                                    res_medic = o_medic

        return x_dst, y_dst, res_medic

    def win_or_draw(self):
        """
        if the game has winner the first value of returning tuple is 0, and second value of tuple is winner and third is loser
        if the game is draw the first value of returning tuple is 1, and second and third value of tuple is just team names
        """
        no_medics_1 = len(self.world.medics[self.sides[0]])
        no_medics_2 = len(self.world.medics[self.sides[1]])
        if no_medics_1 != no_medics_2:
            if no_medics_1 == 0:
                return 0, self.sides[1], self.sides[0]
            if no_medics_2 == 0:
                return 0, self.sides[0], self.sides[1]

        score_1 = self.world.scores[self.sides[0]]
        score_2 = self.world.scores[self.sides[1]]

        if score_1 == score_2:
            return 1, self.sides[0], self.sides[1]
        elif score_1 > score_2:
            return 0, self.sides[0], self.sides[1]
        else:
            return 0, self.sides[1], self.sides[0]

    def _reload_laser_count(self):
        for side in self.world.medics:
            for medic in self.world.medics[side]:
                if medic.laser_max_count != medic.laser_count:
                    medic.time_to_reload -= 1
                    if medic.time_to_reload == 0:
                        medic.time_to_reload = medic.reload_time
                        if medic.laser_count < medic.laser_max_count:
                            medic.laser_count += 1

    def _get_fire_max_point(self, x1, y1, angle):
        x = x1 + math.cos(math.radians(angle)) * self.world_map["medics"]["laser_range"]
        y = y1 + math.sin(math.radians(angle)) * self.world_map["medics"]["laser_range"]
        return x, y

    @staticmethod
    def get_line_degree_with_2_points(x1, y1, x2, y2):

        if x2 - x1 == 0.0:
            return 90.0 if y2 - y1 > 0 else 270.0
        else:
            if x2 - x1 > 0 and y2 - y1 > 0:
                return math.degrees(math.atan((y2 - y1) / (x2 - x1)))
            elif x2 - x1 < 0 < y2 - y1 > 0:
                return math.degrees(math.atan((y2 - y1) / (x2 - x1))) + 180.0
            elif x2 - x1 < 0 and y2 - y1 < 0:
                return math.degrees(math.atan((y2 - y1) / (x2 - x1))) + 180.0
            else:
                return (math.degrees(math.atan((y2 - y1) / (x2 - x1)) + 360.0)) % 360

    @staticmethod
    def get_lines_meet_point(line_eq1, line_eq2):
        # also may use to solve 2in2 matrix
        # lines equation: ax + by + c = 0
        a1 = line_eq1[0]
        b1 = line_eq1[1]
        c1 = line_eq1[2]

        a2 = line_eq2[0]
        b2 = line_eq2[1]
        c2 = line_eq2[2]

        det = a1 * b2 - b1 * a2
        if det == 0.0:
            return
        else:
            x = (b2 * (-c1) + ((-b1) * (-c2))) / det
            y = ((-a2) * (-c1) + (a1 * (-c2))) / det
            return x, y

    @staticmethod
    def get_line_and_circle_meet_point(r, center_pos, start_pos):
        pass

    @staticmethod
    def get_point_and_circle_tangent_point(r, center_pos, start_pos):
        pass

    def check_crush_line_and_circle(self, r, circle_pos, line_eq, x, y):
        pass

    @staticmethod
    def get_line_formula_by_angle_and_point(x, y, angle):
        if angle == 90.0 or angle == 270.0:
            return [1.0, 0.0, x]  # ax + by + c = 0
        else:
            return [-1 * math.tan(math.radians(angle)), 1, math.tan(math.radians(angle)) * x - y]

    @staticmethod
    def get_2_points_distance(x1, y1, x2, y2):
        return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    @staticmethod
    def has_line_and_circle_meet_point(x_src, y_src, x_dst, y_dst, line_eq, x, y, r):
        a, b, c = line_eq
        dist = (x * a + y * b + c) / (a**2 + b**2)**0.5
        if dist <= r:
            x_tmp, y_tmp, x1_tmp, y1_tmp, x2_tmp, y2_tmp, = [None for _ in range(6)]
            if a == 0:
                y_tmp = -c / b
                delta = (-2 * x)**2 - 4 * (x ** 2 + (y_tmp - y)**2 - r **2)
                if delta > 0:
                    x1_tmp = ((2 * x) + delta**0.5) / 2.0
                    x2_tmp = ((2 * x) - delta**0.5) / 2.0
                elif delta == 0:
                    x_tmp = x
                else:
                    return False
            elif b == 0:
                x_tmp = -c / a
                delta = (-2 * y)**2 - 4 * (y ** 2 + (x_tmp - x)**2 - r **2)
                if delta > 0:
                    y1_tmp = ((2 * y) + delta**0.5) / 2.0
                    y2_tmp = ((2 * y) - delta**0.5) / 2.0
                elif delta == 0:
                    y_tmp = y
                else:
                    return False
            else:
                delta = (-2 * a**2 * y + 2 * a * b * x + 2 * b * c)**2 - 4 * (a**2 + b **2) * (a**2 * x**2 + a**2 * y**2 + 2 * a * c * x + c**2 - a**2 * r**2)
                if delta > 0:
                    y1_tmp = (-(-2 * a**2 * y + 2 * a * b * x + 2 * b * c) + delta**0.5) / (2 * (a**2 + b**2))
                    y2_tmp = (-(-2 * a**2 * y + 2 * a * b * x + 2 * b * c) - delta**0.5) / (2 * (a**2 + b**2))
                    x1_tmp = (-c - b * y1_tmp) / a
                    x2_tmp = (-c - b * y2_tmp) / a
                elif delta == 0:
                    y_tmp = (-(-2 * a**2 * y + 2 * a * b * x + 2 * b * c)) / (2 * (a**2 + b**2))
                    x_tmp = (-c - b * y_tmp) / a

                else:
                    return False
            if x2_tmp is not None and y2_tmp is not None:
                vl = (x_dst - x_src, y_dst - y_src)
                vm1 = (x1_tmp - x_src, y1_tmp - y_src)
                vm2 = (x2_tmp - x_src, y2_tmp - y_src)

                if vl[0]*vm1[0] + vl[1]*vm1[1] > 0:
                    if vl[0]*vm2[0] + vl[1]*vm2[1] > 0:
                        d = (vl[0]**2 + vl[1]**2)**0.5
                        d1 = (vm1[0]**2 + vm1[1]**2)**0.5
                        d2 = (vm2[0]**2 + vm2[1]**2)**0.5
                        if d1 <= d2 and d1 <= d:
                            return True
                        elif d2 <= d1 and d2 < d:
                            return True
                    else:
                        d = (vl[0]**2 + vl[1]**2)**0.5
                        d1 = (vm1[0]**2 + vm1[1]**2)**0.5
                        if d1 <= d:
                            return True
                else:
                    if vl[0]*vm2[0] + vl[1]*vm2[1] > 0:
                        d = (vl[0]**2 + vl[1]**2)**0.5
                        d2 = (vm2[0]**2 + vm2[1]**2)**0.5
                        if d2 <= d:
                            return True
            elif x2_tmp is not None and y_tmp is not None:
                vl = (x_dst - x_src, y_dst - y_src)
                vm1 = (x1_tmp - x_src, y_tmp - y_src)
                vm2 = (x2_tmp - x_src, y_tmp - y_src)
                if vl[0]*vm1[0] + vl[1]*vm1[1] > 0:
                    if vl[0]*vm2[0] + vl[1]*vm2[1] > 0:
                        d = (vl[0]**2 + vl[1]**2)**0.5
                        d1 = (vm1[0]**2 + vm1[1]**2)**0.5
                        d2 = (vm2[0]**2 + vm2[1]**2)**0.5
                        if d1 <= d2 and d1 <= d:
                            return True
                        elif d2 <= d1 and d2 < d:
                            return True
                    else:
                        d = (vl[0]**2 + vl[1]**2)**0.5
                        d1 = (vm1[0]**2 + vm1[1]**2)**0.5
                        if d1 <= d:
                            return True
                else:
                    if vl[0]*vm2[0] + vl[1]*vm2[1] > 0:
                        d = (vl[0]**2 + vl[1]**2)**0.5
                        d2 = (vm2[0]**2 + vm2[1]**2)**0.5
                        if d2 <= d:
                            return True

            elif y2_tmp is not None and x_tmp is not None:
                vl = (x_dst - x_src, y_dst - y_src)
                vm1 = (x_tmp - x_src, y1_tmp - y_src)
                vm2 = (x_tmp - x_src, y2_tmp - y_src)
                if vl[0]*vm1[0] + vl[1]*vm1[1] > 0:
                    if vl[0]*vm2[0] + vl[1]*vm2[1] > 0:
                        d = (vl[0]**2 + vl[1]**2)**0.5
                        d1 = (vm1[0]**2 + vm1[1]**2)**0.5
                        d2 = (vm2[0]**2 + vm2[1]**2)**0.5
                        if d1 <= d2 and d1 <= d:
                            return True
                        elif d2 <= d1 and d2 < d:
                            return True
                    else:
                        d = (vl[0]**2 + vl[1]**2)**0.5
                        d1 = (vm1[0]**2 + vm1[1]**2)**0.5
                        if d1 <= d:
                            return True
                else:
                    if vl[0]*vm2[0] + vl[1]*vm2[1] > 0:
                        d = (vl[0]**2 + vl[1]**2)**0.5
                        d2 = (vm2[0]**2 + vm2[1]**2)**0.5
                        if d2 <= d:
                            return True
            elif x_tmp is not None and y_tmp is not None:
                vl = (x_dst - x_src, y_dst - y_src)
                vm = (x_tmp - x_src, y_tmp - y_src)
                if vl[0]*vm[0] + vl[1]*vm[1] > 0:
                    d = (vl[0]**2 + vl[1]**2)**0.5
                    d1 = (vm[0]**2 + vm[1]**2)**0.5
                    if d1 <= d:
                        return True
        return False

    @staticmethod
    def confidence_of_map_bound():
        return [[{"x": 0.01, "y": 0.01}, {"x": 19.99, "y": 0.01}],
                [{"x": 0.01, "y": 0.01}, {"x": 0.01, "y": 19.99}],
                [{"x": 19.99, "y": 0.01}, {"x": 19.99, "y": 19.99}],
                [{"x": 0.01, "y": 19.99}, {"x": 19.99, "y": 19.99}]]
