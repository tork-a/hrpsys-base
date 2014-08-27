#!/usr/bin/env python

import os
import rtm

from rtm import *
from OpenHRP import *
from hrpsys import *  # load ModelLoader

import socket
import time

# copy from transformations.py, Christoph Gohlke, The Regents of the University of California

import numpy
# map axes strings to/from tuples of inner axis, parity, repetition, frame
_AXES2TUPLE = {
    'sxyz': (0, 0, 0, 0), 'sxyx': (0, 0, 1, 0), 'sxzy': (0, 1, 0, 0),
    'sxzx': (0, 1, 1, 0), 'syzx': (1, 0, 0, 0), 'syzy': (1, 0, 1, 0),
    'syxz': (1, 1, 0, 0), 'syxy': (1, 1, 1, 0), 'szxy': (2, 0, 0, 0),
    'szxz': (2, 0, 1, 0), 'szyx': (2, 1, 0, 0), 'szyz': (2, 1, 1, 0),
    'rzyx': (0, 0, 0, 1), 'rxyx': (0, 0, 1, 1), 'ryzx': (0, 1, 0, 1),
    'rxzx': (0, 1, 1, 1), 'rxzy': (1, 0, 0, 1), 'ryzy': (1, 0, 1, 1),
    'rzxy': (1, 1, 0, 1), 'ryxy': (1, 1, 1, 1), 'ryxz': (2, 0, 0, 1),
    'rzxz': (2, 0, 1, 1), 'rxyz': (2, 1, 0, 1), 'rzyz': (2, 1, 1, 1)}

# axis sequences for Euler angles
_NEXT_AXIS = [1, 2, 0, 1]

# epsilon for testing whether a number is close to zero
_EPS = numpy.finfo(float).eps * 4.0


def euler_matrix(ai, aj, ak, axes='sxyz'):
    """Return homogeneous rotation matrix from Euler angles and axis sequence.

    ai, aj, ak : Euler's roll, pitch and yaw angles
    axes : One of 24 axis sequences as string or encoded tuple

    >>> R = euler_matrix(1, 2, 3, 'syxz')
    >>> numpy.allclose(numpy.sum(R[0]), -1.34786452)
    True
    >>> R = euler_matrix(1, 2, 3, (0, 1, 0, 1))
    >>> numpy.allclose(numpy.sum(R[0]), -0.383436184)
    True
    >>> ai, aj, ak = (4.0*math.pi) * (numpy.random.random(3) - 0.5)
    >>> for axes in _AXES2TUPLE.keys():
    ...    R = euler_matrix(ai, aj, ak, axes)
    >>> for axes in _TUPLE2AXES.keys():
    ...    R = euler_matrix(ai, aj, ak, axes)

    """
    try:
        firstaxis, parity, repetition, frame = _AXES2TUPLE[axes]
    except (AttributeError, KeyError):
        _ = _TUPLE2AXES[axes]
        firstaxis, parity, repetition, frame = axes

    i = firstaxis
    j = _NEXT_AXIS[i + parity]
    k = _NEXT_AXIS[i - parity + 1]

    if frame:
        ai, ak = ak, ai
    if parity:
        ai, aj, ak = -ai, -aj, -ak

    si, sj, sk = math.sin(ai), math.sin(aj), math.sin(ak)
    ci, cj, ck = math.cos(ai), math.cos(aj), math.cos(ak)
    cc, cs = ci * ck, ci * sk
    sc, ss = si * ck, si * sk

    M = numpy.identity(4)
    if repetition:
        M[i, i] = cj
        M[i, j] = sj * si
        M[i, k] = sj * ci
        M[j, i] = sj * sk
        M[j, j] = -cj * ss + cc
        M[j, k] = -cj * cs - sc
        M[k, i] = -sj * ck
        M[k, j] = cj * sc + cs
        M[k, k] = cj * cc - ss
    else:
        M[i, i] = cj * ck
        M[i, j] = sj * sc - cs
        M[i, k] = sj * cc + ss
        M[j, i] = cj * sk
        M[j, j] = sj * ss + cc
        M[j, k] = sj * cs - sc
        M[k, i] = -sj
        M[k, j] = cj * si
        M[k, k] = cj * ci
    return M


def euler_from_matrix(matrix, axes='sxyz'):
    """Return Euler angles from rotation matrix for specified axis sequence.

    axes : One of 24 axis sequences as string or encoded tuple

    Note that many Euler angle triplets can describe one matrix.

    >>> R0 = euler_matrix(1, 2, 3, 'syxz')
    >>> al, be, ga = euler_from_matrix(R0, 'syxz')
    >>> R1 = euler_matrix(al, be, ga, 'syxz')
    >>> numpy.allclose(R0, R1)
    True
    >>> angles = (4.0*math.pi) * (numpy.random.random(3) - 0.5)
    >>> for axes in _AXES2TUPLE.keys():
    ...    R0 = euler_matrix(axes=axes, *angles)
    ...    R1 = euler_matrix(axes=axes, *euler_from_matrix(R0, axes))
    ...    if not numpy.allclose(R0, R1): print axes, "failed"

    """
    try:
        firstaxis, parity, repetition, frame = _AXES2TUPLE[axes.lower()]
    except (AttributeError, KeyError):
        _ = _TUPLE2AXES[axes]
        firstaxis, parity, repetition, frame = axes

    i = firstaxis
    j = _NEXT_AXIS[i + parity]
    k = _NEXT_AXIS[i - parity + 1]

    M = numpy.array(matrix, dtype=numpy.float64, copy=False)[:3, :3]
    if repetition:
        sy = math.sqrt(M[i, j] * M[i, j] + M[i, k] * M[i, k])
        if sy > _EPS:
            ax = math.atan2(M[i, j], M[i, k])
            ay = math.atan2(sy, M[i, i])
            az = math.atan2(M[j, i], -M[k, i])
        else:
            ax = math.atan2(-M[j, k], M[j, j])
            ay = math.atan2(sy, M[i, i])
            az = 0.0
    else:
        cy = math.sqrt(M[i, i] * M[i, i] + M[j, i] * M[j, i])
        if cy > _EPS:
            ax = math.atan2(M[k, j], M[k, k])
            ay = math.atan2(-M[k, i], cy)
            az = math.atan2(M[j, i], M[i, i])
        else:
            ax = math.atan2(-M[j, k], M[j, j])
            ay = math.atan2(-M[k, i], cy)
            az = 0.0

    if parity:
        ax, ay, az = -ax, -ay, -az
    if frame:
        ax, az = az, ax
    return ax, ay, az


# class for configure hrpsys RTCs and ports
#   In order to specify robot-dependent code, please inherit this HrpsysConfigurator
class HrpsysConfigurator:

    # RobotHardware
    rh = None
    rh_svc = None
    ep_svc = None

    # SequencePlayer
    seq = None
    seq_svc = None

    # StateHolder
    sh = None
    sh_svc = None

    # ForwardKinematics
    fk = None
    fk_svc = None

    tf = None  # TorqueFilter
    kf = None  # KalmanFilter
    vs = None  # VirtualForceSensor
    rmfo = None  # RemoveForceSensorLinkOffset
    ic = None  # ImpedanceController
    abc = None  # AutoBalancer
    st = None  # Stabilizer

    # CollisionDetector
    co = None
    co_svc = None

    # GraspController
    gc = None
    gc_svc = None

    # SoftErrorLimiter
    el = None
    el_svc = None

    # ThermoEstimator
    te = None
    te_svc = None

    # ThermoLimiter
    tl = None
    tl_svc = None

    # TorqueController
    tc = None
    tc_svc = None

    # DataLogger
    log = None
    log_svc = None

    # rtm manager
    ms = None

    # HGController(Simulation)
    hgc = None

    # PDController(Simulation)
    pdc = None

    # flag isSimulation?
    simulation_mode = None

    # sensors
    sensors = None

    # for setSelfGroups
    Groups = []  # [['torso', ['CHEST_JOINT0']], ['head', ['HEAD_JOINT0', 'HEAD_JOINT1']], ....]

    # public method
    def connectComps(self):
        if self.rh == None or self.seq == None or self.sh == None or self.fk == None:
            print self.configurator_name, "\e[1;31m connectComps : hrpsys requries rh, seq, sh and fk, please check rtcd.conf or rtcd arguments\e[0m"
            return
        # connection for reference joint angles
        tmp_contollers = self.getJointAngleControllerList()
        if len(tmp_contollers) > 0:
            connectPorts(self.sh.port("qOut"), tmp_contollers[0].port("qRef"))
            for i in range(len(tmp_contollers) - 1):
                connectPorts(tmp_contollers[i].port("q"),
                             tmp_contollers[i + 1].port("qRef"))
            if self.simulation_mode:
                if self.pdc:
                    connectPorts(tmp_contollers[-1].port("q"), self.pdc.port("angleRef"))
                else:
                    connectPorts(tmp_contollers[-1].port("q"), self.hgc.port("qIn"))
                    connectPorts(self.hgc.port("qOut"), self.rh.port("qRef"))
            else:
                connectPorts(tmp_contollers[-1].port("q"), self.rh.port("qRef"))
        else:
            if self.simulation_mode:
                if self.pdc:
                    connectPorts(self.sh.port("qOut"), self.pdc.port("angleRef"))
                else:
                    connectPorts(self.sh.port("qOut"), self.hgc.port("qIn"))
                    connectPorts(self.hgc.port("qOut"), self.rh.port("qRef"))
            else:
                connectPorts(self.sh.port("qOut"), self.rh.port("qRef"))

        # connection for kf
        if self.kf:
            #   currently use first acc and rate sensors for kf
            s_acc = filter(lambda s: s.type == 'Acceleration', self.sensors)
            if (len(s_acc) > 0) and self.rh.port(s_acc[0].name) != None:  # check existence of sensor ;; currently original HRP4C.xml has different naming rule of gsensor and gyrometer
                connectPorts(self.rh.port(s_acc[0].name), self.kf.port('acc'))
            s_rate = filter(lambda s: s.type == 'RateGyro', self.sensors)
            if (len(s_rate) > 0) and self.rh.port(s_rate[0].name) != None:  # check existence of sensor ;; currently original HRP4C.xml has different naming rule of gsensor and gyrometer
                connectPorts(self.rh.port(s_rate[0].name), self.kf.port("rate"))

        # connection for rh
        if self.rh.port("servoState") != None:
            if self.te and self.el:
                connectPorts(self.rh.port("servoState"),
                             self.te.port("servoStateIn"))
                connectPorts(self.te.port("servoStateOut"),
                             self.el.port("servoStateIn"))
            elif self.el:
                connectPorts(self.rh.port("servoState"),
                             self.el.port("servoStateIn"))
            elif self.te:
                connectPorts(self.rh.port("servoState"),
                             self.te.port("servoStateIn"))

        # connection for sh, seq, fk
        connectPorts(self.rh.port("q"), [self.sh.port("currentQIn"),
                                         self.fk.port("q")])  # connection for actual joint angles
        connectPorts(self.sh.port("qOut"), self.fk.port("qRef"))
        connectPorts(self.seq.port("qRef"), self.sh.port("qIn"))
        connectPorts(self.seq.port("tqRef"), self.sh.port("tqIn"))
        connectPorts(self.seq.port("basePos"), self.sh.port("basePosIn"))
        connectPorts(self.seq.port("baseRpy"), self.sh.port("baseRpyIn"))
        connectPorts(self.seq.port("zmpRef"), self.sh.port("zmpIn"))
        connectPorts(self.sh.port("basePosOut"), [self.seq.port("basePosInit"),
                                                  self.fk.port("basePosRef")])
        connectPorts(self.sh.port("baseRpyOut"), [self.seq.port("baseRpyInit"),
                                                  self.fk.port("baseRpyRef")])
        connectPorts(self.sh.port("qOut"), self.seq.port("qInit"))
        connectPorts(self.sh.port("zmpOut"), self.seq.port("zmpRefInit"))
        for sen in filter(lambda x: x.type == "Force", self.sensors):
            connectPorts(self.seq.port(sen.name + "Ref"),
                         self.sh.port(sen.name + "In"))

        # connection for st
        if rtm.findPort(self.rh.ref, "lfsensor") and rtm.findPort(
                                     self.rh.ref, "rfsensor") and self.st:
            connectPorts(self.rh.port("lfsensor"), self.st.port("forceL"))
            connectPorts(self.rh.port("rfsensor"), self.st.port("forceR"))
            connectPorts(self.kf.port("rpy"), self.st.port("rpy"))
            connectPorts(self.abc.port("zmpRef"), self.st.port("zmpRef"))
            connectPorts(self.abc.port("baseRpy"), self.st.port("baseRpyIn"))
            connectPorts(self.abc.port("basePos"), self.st.port("basePosIn"))
            connectPorts(self.abc.port("accRef"), self.kf.port("accRef"))
            connectPorts(self.abc.port("contactStates"), self.st.port("contactStates"))
            connectPorts(self.rh.port("q"), self.st.port("qCurrent"))
        if self.ic and self.abc:
            for sen in filter(lambda x: x.type == "Force", self.sensors):
                connectPorts(self.ic.port("ref_" + sen.name),
                             self.abc.port("ref_" + sen.name))

        #  actual force sensors
        if self.rmfo:
            if self.kf: # use IMU values if exists
                # connectPorts(self.kf.port("rpy"), self.ic.port("rpy"))
                connectPorts(self.kf.port("rpy"), self.rmfo.port("rpy"))
            connectPorts(self.rh.port("q"), self.rmfo.port("qCurrent"))
            for sen in filter(lambda x: x.type == "Force", self.sensors):
                connectPorts(self.rh.port(sen.name), self.rmfo.port(sen.name))
                if self.ic:
                    connectPorts(self.rmfo.port("off_" + sen.name),
                                 self.ic.port(sen.name))
        # connection for ic
        if self.ic:
            connectPorts(self.rh.port("q"), self.ic.port("qCurrent"))
        # connection for tf
        if self.tf:
            # connection for actual torques
            if rtm.findPort(self.rh.ref, "tau") != None:
                connectPorts(self.rh.port("tau"), self.tf.port("tauIn"))
            connectPorts(self.rh.port("q"), self.tf.port("qCurrent"))
        # connection for vs
        if self.vs:
            connectPorts(self.rh.port("q"), self.vs.port("qCurrent"))
            connectPorts(self.tf.port("tauOut"), self.vs.port("tauIn"))
            #  virtual force sensors
            if self.ic:
                for vfp in filter(lambda x: str.find(x, 'v') >= 0 and
                                  str.find(x, 'sensor') >= 0, self.vs.ports.keys()):
                    connectPorts(self.vs.port(vfp), self.ic.port(vfp))
        # connection for co
        if self.co:
            connectPorts(self.rh.port("q"), self.co.port("qCurrent"))

        # connection for gc
        if self.gc:
            connectPorts(self.rh.port("q"), self.gc.port("qCurrent"))  # other connections
            tmp_controller = self.getJointAngleControllerList()
            index = tmp_controller.index(self.gc)
            if index == 0:
                connectPorts(self.sh.port("qOut"), self.gc.port("qIn"))
            else:
                connectPorts(tmp_controller[index - 1].port("q"),
                             self.gc.port("qIn"))

        # connection for te
        if self.te:
            if self.tf:
                connectPorts(self.tf.port("tauOut"), self.te.port("tauIn"))
            else:
                connectPorts(self.rh.port("tau"), self.te.port("tauIn"))
            # sevoStateIn is connected above

        # connection for tl
        if self.tl:
            if self.tf:
                connectPorts(self.tf.port("tauOut"), self.tl.port("tauIn"))
            else:
                connectPorts(self.rh.port("tau"), self.tl.port("tauIn"))
            if self.te:
                connectPorts(self.te.port("tempOut"), self.tl.port("tempIn"))
            connectPorts(self.rh.port("q"), self.tl.port("qCurrentIn"))
            # qRef is connected as joint angle controller

        # connection for tc
        if self.tc:
            connectPorts(self.rh.port("q"), self.tc.port("qCurrent"))
            if self.tf:
                connectPorts(self.tf.port("tauOut"),
                             self.tc.port("tauCurrent"))
            else:
                connectPorts(self.rh.port("tau"), self.tc.port("tauCurrent"))
            if self.tl:
                connectPorts(self.tl.port("tauMax"), self.tc.port("tauMax"))

        # connection for el
        if self.el:
            connectPorts(self.rh.port("q"), self.el.port("qCurrent"))

    def activateComps(self):
        rtcList = self.getRTCInstanceList()
        rtm.serializeComponents(rtcList)
        for r in rtcList:
            r.start()

    def createComp(self, compName, instanceName):
        self.ms.load(compName)
        comp = self.ms.create(compName, instanceName)
        print self.configurator_name, "create Comp -> ", compName, " : ", comp
        if comp == None:
            raise RuntimeError("Cannot create component: " + compName)
        if comp.service("service0"):
            comp_svc = narrow(comp.service("service0"), compName + "Service")
            print self.configurator_name, "create CompSvc -> ", compName, "Service : ", comp_svc
            return [comp, comp_svc]
        else:
            return [comp, None]

    def createComps(self):
        for rn in self.getRTCList():
            rn2 = 'self.' + rn[0]
            if eval(rn2) == None:
                create_str = "[self." + rn[0] + ", self." + rn[0] + "_svc] = self.createComp(\"" + rn[1] + "\",\"" + rn[0] + "\")"
                print self.configurator_name, "  eval : ", create_str
                exec(create_str)

    def findComp(self, compName, instanceName, max_timeout_count=10):
        timeout_count = 0
        comp = rtm.findRTC(instanceName)
        while comp == None and timeout_count < max_timeout_count:
            comp = rtm.findRTC(instanceName)
            if comp != None:
                break
            print self.configurator_name, " find Comp wait for", instanceName
            time.sleep(1)
            timeout_count += 1
        print self.configurator_name, " find Comp    : ", instanceName, " = ", comp
        if comp == None:
            print self.configurator_name, " Cannot find component: " + instanceName + " (" + compName + ")"
            return [None, None]
        if comp.service("service0"):
            comp_svc = narrow(comp.service("service0"), compName + "Service")
            print self.configurator_name, " find CompSvc : ", instanceName + "_svc = ", comp_svc
            return [comp, comp_svc]
        else:
            return [comp, None]

    def findComps(self):
        max_timeout_count = 10
        for rn in self.getRTCList():
            rn2 = 'self.' + rn[0]
            if eval(rn2) == None:
                create_str = "[self." + rn[0] + ", self." + rn[0] + "_svc] = self.findComp(\"" + rn[1] + "\",\"" + rn[0] + "\"," + str(max_timeout_count) + ")"
                print self.configurator_name, create_str
                exec(create_str)
                if eval(rn2) == None:
                    max_timeout_count = 0

    # public method to configure all RTCs to be activated on rtcd
    def getRTCList(self):
        '''
        @rtype: list of list
        @return: List of available components. Each element consists of a list
                 of abbreviated and full names of the component.
        '''
        return [
            ['seq', "SequencePlayer"],
            ['sh', "StateHolder"],
            ['fk', "ForwardKinematics"],
            # ['tf', "TorqueFilter"],
            # ['kf', "KalmanFilter"],
            # ['vs', "VirtualForceSensor"],
            # ['rmfo', "RemoveForceSensorLinkOffset"],
            # ['ic', "ImpedanceController"],
            # ['abc', "AutoBalancer"],
            # ['st', "Stabilizer"],
            ['co', "CollisionDetector"],
            # ['tc', "TorqueController"],
            # ['te', "ThermoEstimator"],
            # ['tl', "ThermoLimiter"],
            ['el', "SoftErrorLimiter"],
            ['log', "DataLogger"]
            ]

    # public method to configure all RTCs to be activated on rtcd which includes unstable RTCs
    def getRTCListUnstable(self):
        '''
        @rtype: list of list
        @return: List of available unstable components. Each element consists
                 of a list of abbreviated and full names of the component.
        '''
        return [
            ['seq', "SequencePlayer"],
            ['sh', "StateHolder"],
            ['fk', "ForwardKinematics"],
            ['tf', "TorqueFilter"],
            ['kf', "KalmanFilter"],
            ['vs', "VirtualForceSensor"],
            ['rmfo', "RemoveForceSensorLinkOffset"],
            ['ic', "ImpedanceController"],
            ['abc', "AutoBalancer"],
            ['st', "Stabilizer"],
            ['co', "CollisionDetector"],
            ['tc', "TorqueController"],
            # ['te', "ThermoEstimator"],
            # ['tl', "ThermoLimiter"],
            ['el', "SoftErrorLimiter"],
            ['log', "DataLogger"]
            ]

    def getJointAngleControllerList(self):
        controller_list = [self.ic, self.gc, self.abc, self.st, self.co,
                           self.tc, self.el]
        return filter(lambda c: c != None, controller_list)  # only return existing controllers

    def getRTCInstanceList(self):
        ret = [self.rh]
        for r in map(lambda x: 'self.' + x[0], self.getRTCList()):
            ret.append(eval(r))
        return ret

    # public method to get bodyInfo
    def getBodyInfo(self, url):
        import CosNaming
        obj = rtm.rootnc.resolve([CosNaming.NameComponent('ModelLoader', '')])
        mdlldr = obj._narrow(ModelLoader_idl._0_OpenHRP__POA.ModelLoader)
        print self.configurator_name, "  bodyinfo URL = file://" + url
        return mdlldr.getBodyInfo("file://" + url)

    # public method to get sensors list
    def getSensors(self, url):
        if url == '':
            return []
        else:
            return sum(map(lambda x: x.sensors,
                           filter(lambda x: len(x.sensors) > 0,
                                  self.getBodyInfo(url)._get_links())), [])  # sum is for list flatten

    def connectLoggerPort(self, artc, sen_name, log_name=None):
        log_name = log_name if log_name else artc.name() + "_" + sen_name
        if artc and rtm.findPort(artc.ref, sen_name) != None:
            sen_type = rtm.dataTypeOfPort(artc.port(sen_name)).split("/")[1].split(":")[0]
            if rtm.findPort(self.log.ref, log_name) == None:
                print self.configurator_name, "  setupLogger : record type =", sen_type, ", name = ", sen_name, " to ", log_name
                self.log_svc.add(sen_type, log_name)
            else:
                print self.configurator_name, "  setupLogger : ", sen_name, " arleady exists in DataLogger"
            connectPorts(artc.port(sen_name), self.log.port(log_name))

    # public method to configure default logger data ports
    def setupLogger(self):
        if self.log == None:
            print self.configurator_name, "\e[1;31m  setupLogger : self.log is not defined, please check rtcd.conf or rtcd arguments\e[0m"
            return
        #
        for pn in ['q', 'tau']:
            self.connectLoggerPort(self.rh, pn)
        # sensor logger ports
        print self.configurator_name, "sensor names for DataLogger"
        for sen in self.sensors:
            self.connectLoggerPort(self.rh, sen.name)
        #
        if self.kf != None:
            self.connectLoggerPort(self.kf, 'rpy')
        if self.seq != None:
            self.connectLoggerPort(self.seq, 'qRef')
        if self.sh != None:
            self.connectLoggerPort(self.sh, 'qOut')
            self.connectLoggerPort(self.sh, 'tqOut')
            self.connectLoggerPort(self.sh, 'basePosOut')
            self.connectLoggerPort(self.sh, 'baseRpyOut')
            self.connectLoggerPort(self.sh, 'zmpOut')
        if self.abc != None:
            self.connectLoggerPort(self.abc, 'zmpRef')
            self.connectLoggerPort(self.abc, 'baseTformOut')
            self.connectLoggerPort(self.abc, 'q')
        if self.st != None:
            self.connectLoggerPort(self.st, 'zmp')
            self.connectLoggerPort(self.st, 'originRefZmp')
            self.connectLoggerPort(self.st, 'originRefCog')
            self.connectLoggerPort(self.st, 'originRefCogVel')
            self.connectLoggerPort(self.st, 'originNewZmp')
            self.connectLoggerPort(self.st, 'originActZmp')
            self.connectLoggerPort(self.st, 'originActCog')
            self.connectLoggerPort(self.st, 'originActCogVel')
            self.connectLoggerPort(self.st, 'refWrenchR')
            self.connectLoggerPort(self.st, 'refWrenchL')
            self.connectLoggerPort(self.st, 'footCompR')
            self.connectLoggerPort(self.st, 'footCompL')
        if self.rh != None:
            self.connectLoggerPort(self.rh, 'emergencySignal',
                                   'emergencySignal')
        for sen in filter(lambda x: x.type == "Force", self.sensors):
            self.connectLoggerPort(self.seq, sen.name + "Ref")
        self.log_svc.clear()

    def waitForRTCManager(self, managerhost=nshost):
        self.ms = None
        while self.ms == None:
            time.sleep(1)
            if managerhost == "localhost":
                managerhost = socket.gethostname()
            self.ms = rtm.findRTCmanager(managerhost)
            print self.configurator_name, "wait for RTCmanager : ", managerhost

    def waitForRobotHardware(self, robotname="Robot"):
        self.rh = None
        timeout_count = 0
        # wait for simulator or RobotHardware setup which sometime takes a long time
        while self.rh == None and timeout_count < 10:  # <- time out limit
            time.sleep(1);
            self.rh = rtm.findRTC("RobotHardware0")
            if not self.rh:
                self.rh = rtm.findRTC(robotname)
            print self.configurator_name, "wait for", robotname, " : ", self.rh, "(timeout ", timeout_count, " < 10)"
            if self.rh and self.rh.isActive() == None:  # just in case rh is not ready...
                self.rh = None
            timeout_count += 1

        if not self.rh:
            print self.configurator_name, "Could not find ", robotname
            if self.ms:
                print self.configurator_name, "Candidates are .... ", [x.name()  for x in self.ms.get_components()]
            print self.configurator_name, "Exitting.... ", robotname
            exit(1)

        print self.configurator_name, "findComps -> RobotHardware : ", self.rh, "isActive? = ", self.rh.isActive()

    def checkSimulationMode(self):
        # distinguish real robot from simulation by using "servoState" port
        if rtm.findPort(self.rh.ref, "servoState") == None:
            self.hgc = findRTC("HGcontroller0")
            self.pdc = findRTC("PDcontroller0")
            self.simulation_mode = True
        else:
            self.simulation_mode = False
            self.rh_svc = narrow(self.rh.service("service0"), "RobotHardwareService")
            self.ep_svc = narrow(self.rh.ec, "ExecutionProfileService")

        print self.configurator_name, "simulation_mode : ", self.simulation_mode

    def waitForRTCManagerAndRoboHardware(self, robotname="Robot", managerhost=nshost):
        self.waitForRTCManager(managerhost)
        self.waitForRobotHardware(robotname)
        self.checkSimulationMode()

    def findModelLoader(self):
        try:
            return rtm.findObject("ModelLoader")
        except:
            return None

    def waitForModelLoader(self):
        while self.findModelLoader() == None:  # seq uses modelloader
            print self.configurator_name, "wait for ModelLoader"
            time.sleep(3)

    def setSelfGroups(self):
        '''
        Set to the hrpsys.SequencePlayer the groups of links and joints that
        are statically defined as member variables (Groups) within this class.
        '''
        for item in self.Groups:
            self.seq_svc.addJointGroup(item[0], item[1])

    # #
    # # service interface for RTC component
    # #
    def goActual(self):
        '''
        Adjust commanded values to the angles in the physical state
        by calling StateHolder::goActual.

        This needs to be run BEFORE servos are turned on.
        '''
        self.sh_svc.goActual()

    def setJointAngle(self, jname, angle, tm):
        '''
        Set angle to the given joint.

        NOTE-1: It's known that this method does not do anything after
                some group operation is done.
                TODO: at least need elaborated to warn users.

        NOTE-2: that while this method does not check angle value range,
        any joints could emit position limit over error, which has not yet
        been thrown by hrpsys so that there's no way to catch on this client
        side. Worthwhile opening an enhancement ticket for that at
        hironx' designated issue tracker.

        @type jname: str
        @type angle: float
        @param angle: In degree.
        @type tm: float
        @param tm: Time to complete.
        '''
        radangle = angle / 180.0 * math.pi
        return self.seq_svc.setJointAngle(jname, radangle, tm)

    def setJointAngles(self, angles, tm):
        '''
        NOTE-1: that while this method does not check angle value range,
                any joints could emit position limit over error, which has not yet
                been thrown by hrpsys so that there's no way to catch on this client
                side. Worthwhile opening an enhancement ticket for that at
                hironx' designated issue tracker.

        @type angles: list of float
        @param angles: In degree.
        @type tm: float
        @param tm: Time to complete.
        '''
        ret = []
        for angle in angles:
            ret.append(angle / 180.0 * math.pi)
        return self.seq_svc.setJointAngles(ret, tm)

    def setJointAnglesOfGroup(self, gname, pose, tm, wait=True):
        '''
        Set the joint angles to aim. By default it waits interpolation to be
        over.

        Note that while this method does not check angle value range,
        any joints could emit position limit over error, which has not yet
        been handled in hrpsys so that there's no way to catch on this client
        class level. Please consider opening an enhancement ticket for that
        at hironx' designated issue tracker.

        @type gname: str
        @param gname: Name of the joint group.
        @type pose: list of float
        @param pose: list of positions and orientations
        @type tm: float
        @param tm: Time to complete.
        @type wait: bool
        @param wait: If true, SequencePlayer.waitInterpolationOfGroup gets run.
                  (TODO: Elaborate what this means...Even after having taken
                  a look at its source code I can't tell exactly what it means)
        '''
        angles = [x / 180.0 * math.pi for x in pose]
        ret = self.seq_svc.setJointAnglesOfGroup(gname, angles, tm)
        if wait:
            self.waitInterpolationOfGroup(gname)
        return ret

    def loadPattern(self, fname, tm):
        '''
        Load a pattern file that is created offline.

        Format of the pattern file:
        - example format:

          t0 j0 j1 j2...jn
          t1 j0 j1 j2...jn
          :
          tn j0 j1 j2...jn

        - Delimmitted by space
        - Each line consists of an action.
        - Time between each action is defined by tn+1 - tn
          - The time taken for the 1st line is defined by the arg tm.

        @param fname: Name of the pattern file.
        @type tm: float
        @param tm: - The time to take for the 1st line.
        @return: List of 2 oct(string) values.
        '''
        return self.seq_svc.loadPattern(fname, tm)

    def waitInterpolation(self):
        self.seq_svc.waitInterpolation()

    def waitInterpolationOfGroup(self, gname):
        '''
        Lets SequencePlayer wait until the movement currently happening to
        finish.

        @see: SequencePlayer.waitInterpolationOfGroup
        @see: http://wiki.ros.org/joint_trajectory_action. This method
              corresponds to JointTrajectoryGoal in ROS.

        @type gname: str
        @param gname: Name of the joint group.
        '''
        self.seq_svc.waitInterpolationOfGroup(gname)

    def getJointAngles(self):
        '''
        @see: HrpsysConfigurator.getJointAngles

        Returns the commanded joint angle values.

        Note that it's not the physical state of the robot's joints, which
        can be obtained by getActualState().angle.

        @rtype: List of float
        @return: List of angles (degree) of all joints, in the order defined
                 in the member variable 'Groups' (eg. chest, head1, head2, ..).
        '''
        return [x * 180.0 / math.pi for x in self.sh_svc.getCommand().jointRefs]

    def getCurrentPose(self, lname=None, frame_name=None):
        '''
        Returns the current physical pose of the specified joint.
        cf. getReferencePose that returns commanded value.

        eg.
             IN: robot.getCurrentPose('LARM_JOINT5')
             OUT: [-0.0017702356144599085,
              0.00019034630541264752,
              -0.9999984150158207,
              0.32556275164378523,
              0.00012155879975329215,
              0.9999999745367515,
               0.0001901314142046251,
               0.18236394191140365,
               0.9999984257434246,
               -0.00012122202968358842,
               -0.001770258707652326,
               0.07462472659364472,
               0.0,
               0.0,
               0.0,
               1.0]

        @type lname: str
        @param lname: Name of the link.
        @rtype: list of float
        @return: Rotational matrix and the position of the given joint in
                 1-dimensional list, that is:

                 [a11, a12, a13, x,
                  a21, a22, a23, y,
                  a31, a32, a33, z,
                   0,   0,   0,  1]
        '''
        if not lname:
            for item in self.Groups:
                eef_name = item[1][-1]
                print("{}: {}".format(eef_name, self.getCurrentPose(eef_name)))
            raise RuntimeError("need to specify joint name")
        if frame_name:
            lname = lname + ':' + frame_name
        pose = self.fk_svc.getCurrentPose(lname)
        if not pose[0]:
            raise RuntimeError("Could not find reference : " + lname)
        return pose[1].data

    def getCurrentPosition(self, lname=None, frame_name=None):
        '''
        Returns the current physical position of the specified joint.
        cf. getReferencePosition that returns commanded value.

        eg.
            robot.getCurrentPosition('LARM_JOINT5')
            [0.325, 0.182, 0.074]

        @type lname: str
        @param lname: Name of the link.
        @rtype: list of float
        @return: List of x, y, z positions about the specified joint.
        '''
        if not lname:
            for item in self.Groups:
                eef_name = item[1][-1]
                print("{}: {}".format(eef_name, self.getCurrentPosition(eef_name)))
            raise RuntimeError("need to specify joint name")
        pose = self.getCurrentPose(lname, frame_name)
        return [pose[3], pose[7], pose[11]]

    def getCurrentRotation(self, lname, frame_name=None):
        '''
        Returns the current physical rotation of the specified joint.
        cf. getReferenceRotation that returns commanded value.

        @type lname: str
        @param lname: Name of the link.
        @rtype: list of float
        @return: Rotational matrix of the given joint in 2-dimensional list,
                 that is:
                 [[a11, a12, a13],
                  [a21, a22, a23],
                  [a31, a32, a33]]
        '''
        if not lname:
            for item in self.Groups:
                eef_name = item[1][-1]
                print("{}: {}".format(eef_name, self.getCurrentRotation(eef_name)))
            raise RuntimeError("need to specify joint name")
        pose = self.getCurrentPose(lname, frame_name)
        return [pose[0:3], pose[4:7], pose[8:11]]

    def getCurrentRPY(self, lname, frame_name=None):
        '''
        Returns the current physical rotation in RPY of the specified joint.
        cf. getReferenceRPY that returns commanded value.

        @type lname: str
        @param lname: Name of the link.
        @rtype: list of float
        @return: List of orientation in rpy form about the specified joint.
        '''
        if not lname:
            for item in self.Groups:
                eef_name = item[1][-1]
                print("{}: {}".format(eef_name, self.getCurrentRPY(eef_name)))
            raise RuntimeError("need to specify joint name")
        return euler_from_matrix(self.getCurrentRotation(lname), 'sxyz')

    def getReferencePose(self, lname, frame_name=None):
        '''
        Returns the current commanded pose of the specified joint.
        cf. getCurrentPose that returns physical pose.

        @type lname: str
        @param lname: Name of the link.
        @rtype: list of float
        @return: Rotational matrix and the position of the given joint in
                 1-dimensional list, that is:

                 [a11, a12, a13, x,
                  a21, a22, a23, y,
                  a31, a32, a33, z,
                   0,   0,   0,  1]
        '''
        if not lname:
            for item in self.Groups:
                eef_name = item[1][-1]
                print("{}: {}".format(eef_name, self.getReferencePose(eef_name)))
            raise RuntimeError("need to specify joint name")
        if frame_name:
            lname = lname + ':' + frame_name
        pose = self.fk_svc.getReferencePose(lname)
        if not pose[0]:
            raise RuntimeError("Could not find reference : " + lname)
        return pose[1].data

    def getReferencePosition(self, lname, frame_name=None):
        '''
        Returns the current commanded position of the specified joint.
        cf. getCurrentPosition that returns physical value.

        @type lname: str
        @param lname: Name of the link.
        @rtype: list of float
        @return: List of angles (degree) of all joints, in the order defined
                 in the member variable 'Groups' (eg. chest, head1, head2, ..).
        '''
        if not lname:
            for item in self.Groups:
                eef_name = item[1][-1]
                print("{}: {}".format(eef_name, self.getReferencePosition(eef_name)))
            raise RuntimeError("need to specify joint name")
        pose = self.getReferencePose(lname, frame_name)
        return [pose[3], pose[7], pose[11]]

    def getReferenceRotation(self, lname, frame_name=None):
        '''
        Returns the current commanded rotation of the specified joint.
        cf. getCurrentRotation that returns physical value.

        @type lname: str
        @param lname: Name of the link.
        @rtype: list of float
        @return: Rotational matrix of the given joint in 2-dimensional list,
                 that is:
                 [[a11, a12, a13],
                  [a21, a22, a23],
                  [a31, a32, a33]]
        '''
        if not lname:
            for item in self.Groups:
                eef_name = item[1][-1]
                print("{}: {}".format(eef_name, self.getReferencePotation(eef_name)))
            raise RuntimeError("need to specify joint name")
        pose = self.getReferencePose(lname, frame_name)
        return [pose[0:3], pose[4:7], pose[8:11]]

    def getReferenceRPY(self, lname, frame_name=None):
        '''
        Returns the current commanded rotation in RPY of the specified joint.
        cf. getCurrentRPY that returns physical value.

        @type lname: str
        @param lname: Name of the link.
        @rtype: list of float
        @return: List of orientation in rpy form about the specified joint.
        '''
        if not lname:
            for item in self.Groups:
                eef_name = item[1][-1]
                print("{}: {}".format(eef_name, self.getReferenceRPY(eef_name)))
            raise RuntimeError("need to specify joint name")
        return euler_from_matrix(self.getReferenceRotation(lname, frame_name), 'sxyz')

    def setTargetPose(self, gname, pos, rpy, tm, frame_name=None):
        '''
        Set absolute pose to a joint.
        All d* arguments are in meter.

        @type gname: str
        @param gname: Name of the joint group.
        @type pos: list of float
        @param pos: In meter.
        @type rpy: list of float
        @param rpy: In radian.
        @type tm: float
        @param tm: Second to complete.
        @type frame_name: str
        @param frame_name: Name of the frame that this particular command
                           reference to.
        @rtype: bool
        @return: False if unreachable.
        '''
        print gname, frame_name, pos, rpy, tm
        if frame_name:
            gname = gname + ':' + frame_name
        result = self.seq_svc.setTargetPose(gname, pos, rpy, tm)
        if not result:
            print("setTargetPose failed. Maybe SequencePlayer failed to solve IK.\n"
                   + "Currently, returning IK result error\n"
                   + "(like the one in https://github.com/start-jsk/rtmros_hironx/issues/103)"
                   + " is not implemented. Patch is welcomed.")
        return result

    def setTargetPoseRelative(self, gname, eename, dx=0, dy=0, dz=0,
dr=0, dp=0, dw=0, tm=10, wait=True):
        '''
        Set angles to a joint group relative to its current pose.

        For d*, distance arguments are in meter while rotations are in degree.

        Example usage: The following moves RARM_JOINT5 joint 0.1mm forward
                       within 0.1sec.

            robot.setTargetPoseRelative('rarm', 'RARM_JOINT5', dx=0.0001,
                                        tm=0.1)

        @type gname: str
        @param gname: Name of the joint group.
        @type eename: str
        @param eename: Name of the link.
        @type dx: float
        @param dx: In meter.
        @type dy: float
        @param dy: In meter.
        @type dz: float
        @param dz: In meter.
        @type dr: float
        @param dr: In radian.
        @type dp: float
        @param dp: In radian.
        @type dw: float
        @param dw: In radian.
        @type tm: float
        @param tm: Second to complete.
        @type wait: bool
        @param wait: If true, SequencePlayer.waitInterpolationOfGroup gets run.
        @rtype: bool
        @return: False if unreachable.
        '''
        self.waitInterpolationOfGroup(gname)
        # curPose = self.getCurrentPose(eename)
        posRef = None
        rpyRef = None
        ret, tds = self.fk_svc.getCurrentPose(eename)
        if ret:
            posRef = numpy.array([tds.data[3], tds.data[7], tds.data[11]])
            rpyRef = numpy.array(euler_from_matrix([tds.data[0:3],
tds.data[4:7], tds.data[8:11]], 'sxyz'))
            posRef += [dx, dy, dz]
            rpyRef += [dr, dp, dw]
            print posRef, rpyRef
            ret = self.setTargetPose(gname, list(posRef), list(rpyRef), tm)
            if ret and wait:
                self.waitInterpolationOfGroup(gname)
            return ret
        return False

    def clear(self):
        '''
        @see HrpsysConfigurator.clear
        Clears the Sequencer's current operation. Works for joint groups too.

        Discussed in https://github.com/fkanehiro/hrpsys-base/issues/158
        Examples is found in a unit test: https://github.com/start-jsk/rtmros_hironx/blob/bb0672be3e03e5366e03fe50520e215302b8419f/hironx_ros_bridge/test/test_hironx.py#L293
        '''
        self.seq_svc.clear()

    def clearOfGroup(self, gname, tm=0.0):
        self.seq_svc.clearOfGroup(gname, tm)

    def saveLog(self, fname='sample'):
        self.log_svc.save(fname)
        print self.configurator_name, "saved data to ", fname

    def clearLog(self):
        self.log_svc.clear()

    def lengthDigitalInput(self):
        return self.rh_svc.lengthDigitalInput()

    def lengthDigitalOutput(self):
        return self.rh_svc.lengthDigitalOutput()

    def writeDigitalOutput(self, dout):
        '''
        Using writeDigitalOutputWithMask is recommended for the less data
        transport.

        @type dout: list of int
        @param dout: List of bits, length of 32 bits where elements are
                     0 or 1.

                     What each element stands for depends on how
                     the robot's imlemented. Consult the hardware manual.
        @rtype: bool
        @return: RobotHardware.writeDigitalOutput returns True if writable. False otherwise.
        '''
        if self.simulation_mode:
            return True
        doutBitLength = self.lengthDigitalOutput() * 8
        if len(dout) < doutBitLength:
            for i in range(doutBitLength - len(dout)):
                dout.append(0)
        outStr = ''
        for i in range(0, len(dout), 8):
            oneChar = 0
            for j in range(8):
                if dout[i + j]:
                    oneChar += 1 << j
            outStr = outStr + chr(oneChar)

        # octet sequences are mapped to strings in omniorbpy
        return self.rh_svc.writeDigitalOutput(outStr)

    def writeDigitalOutputWithMask(self, dout, mask):
        '''
        Both dout and mask are lists with length of 32. Only the bit in dout
        that corresponds to the bits in mask that are flagged as 1 will be
        evaluated.

        Example:
         Case-1. Only 18th bit will be evaluated as 1.
          dout [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
          mask [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

         Case-2. Only 18th bit will be evaluated as 0.
          dout [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
          mask [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

         Case-3. None will be evaluated since there's no flagged bit in mask.
          dout [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
          mask [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

        @type dout: list of int
        @param dout: List of bits, length of 32 bits where elements are
                     0 or 1.
        @type mask: list of int
        @param mask: List of masking bits, length of 32 bits where elements are
                     0 or 1.
        @return: RobotHardware.writeDigitalOutput returns True if writable. False otherwise.
        '''
        if self.simulation_mode:
            return True
        doutBitLength = self.lengthDigitalOutput() * 8
        if len(dout) < doutBitLength and \
               len(mask) < doutBitLength and \
               len(dout) == len(mask):
            for i in range(doutBitLength - len(dout)):
                dout.append(0)
                mask.append(0)
        outStr = ''
        outMsk = ''
        for i in range(0, len(dout), 8):
            oneChar = 0
            oneMask = 0
            for j in range(8):
                if dout[i + j]:
                    oneChar += 1 << j
                if mask[i + j]:
                    oneMask += 1 << j
            outStr = outStr + chr(oneChar)
            outMsk = outMsk + chr(oneMask)

        # octet sequences are mapped to strings in omniorbpy
        return self.rh_svc.writeDigitalOutputWithMask(outStr, outMsk)

    def readDigitalInput(self):
        '''
        @see: HrpsysConfigurator.readDigitalInput

        Digital input consits of 14 bits. The last 2 bits are lacking
        and compensated, so that the last 4 bits are 0x4 instead of 0x1.
        @author Hajime Saito (@emijah)
        @rtype: list of int
        @return: List of the values (2 octtets) in digital input register. Range: 0 or 1.

        #TODO: Catch AttributeError that occurs when RobotHardware not found.
        #      Typically with simulator, erro msg might look like this;
        #      'NoneType' object has no attribute 'readDigitalInput'
        '''
        if self.simulation_mode:
            return []
        ret, din = self.rh_svc.readDigitalInput()
        retList = []
        for item in din:
            for i in range(8):
                if (ord(item) >> i) & 1:
                    retList.append(1)
                else:
                    retList.append(0)
        return retList

    def readDigitalOutput(self):
        '''
        Digital input consits of 14 bits. The last 2 bits are lacking
        and compensated, so that the last 4 bits are 0x4 instead of 0x1.

        #TODO: Catch AttributeError that occurs when RobotHardware not found.
        #      Typically with simulator, erro msg might look like this;
        #      'NoneType' object has no attribute 'readDigitaloutput'

        @author Hajime Saito (@emijah)
        @rtype: list of int
        @return: List of the values in digital input register. Range: 0 or 1.
        '''
        ret, dout = self.rh_svc.readDigitalOutput()
        retList = []
        for item in dout:
            for i in range(8):
                if (ord(item) >> i) & 1:
                    retList.append(1)
                else:
                    retList.append(0)
        return retList

    def getActualState(self):
        '''
        @return: This returns actual states of ther robot, which is defined in
        RobotHardware.idl
        (https://hrpsys-base.googlecode.com/svn/trunk/idl/RobotHardwareService.idl)
            /**
             * @brief status of the robot
             */
            struct RobotState
            {
              DblSequence               angle;  ///< current joint angles[rad]
              DblSequence               command;///< reference joint angles[rad]
              DblSequence               torque; ///< joint torques[Nm]
              /**
               * @brief servo statuses(32bit+extra states)
               *
               * 0: calib status ( 1 => done )\n
               * 1: servo status ( 1 => on )\n
               * 2: power status ( 1 => supplied )\n
               * 3-18: servo alarms (see @ref iob.h)\n
               * 19-23: unused
                       * 24-31: driver temperature (deg)
               */
              LongSequenceSequence              servoState;
              sequence<DblSequence6>    force;    ///< forces[N] and torques[Nm]
              sequence<DblSequence3>    rateGyro; ///< angular velocities[rad/s]
              sequence<DblSequence3>    accel;    ///< accelerations[m/(s^2)]
              double                    voltage;  ///< voltage of power supply[V]
              double                    current;  ///< current[A]
            };
        '''
        return self.rh_svc.getStatus()

    def isCalibDone(self):
        '''
        Check whether joints have been calibrated.
        @rtype bool
        '''
        if self.simulation_mode:
            return True
        else:
            rstt = self.rh_svc.getStatus()
            for item in rstt.servoState:
                if not item[0] & 1:
                    return False
        return True

    def isServoOn(self, jname='any'):
        '''
        Check whether servo control has been turned on.
        @type jname: str
        @param jname: Name of a link (that can be obtained by "hiro.Groups"
                      as lists of groups).
        @rtype bool
        '''
        if self.simulation_mode:
            return True
        else:
            s_s = self.getActualState().servoState
            if jname.lower() == 'any' or jname.lower() == 'all':
                for s in s_s:
                    # print self.configurator_name, 's = ', s
                    if (s[0] & 2) == 0:
                        return False
            else:
                jid = eval('self.' + jname)
                print self.configurator_name, s_s[jid]
                if s_s[jid][0] & 1 == 0:
                    return False
            return True
        return False

    def flat2Groups(self, flatList):
        '''
        @type flatList: list
        @param flatList: single dimension list with its length of 15
        @rtype: list of list
        @return: 2-dimensional list of Groups.
        '''
        retList = []
        index = 0
        for group in self.Groups:
            joint_num = len(group[1])
            retList.append(flatList[index: index + joint_num])
            index += joint_num
        return retList

    def servoOn(self, jname='all', destroy=1, tm=3):
        '''
        Turn on/off servos.
        Joints need to be calibrated (otherwise error returns).

        @type jname: str
        @param jname: The value 'all' works iteratively for all servos.
        @param destroy: Not used.
        @type tm: float
        @param tm: Second to complete.
        @rtype: int
        @return: 1 or -1 indicating success or failure, respectively.
        '''
        # check joints are calibrated
        if not self.isCalibDone():
            waitInputConfirm('!! Calibrate Encoders with checkEncoders first !!\n\n')
            return -1

        # check servo state
        if self.isServoOn():
            return 1

        # check jname is acceptable
        if jname == '':
            jname = 'all'

        try:
            waitInputConfirm(\
                '!! Robot Motion Warning (SERVO_ON) !!\n\n'
                'Confirm RELAY switched ON\n'
                'Push [OK] to switch servo ON(%s).' % (jname))
        except:  # ths needs to change
            self.rh_svc.power('all', SWITCH_OFF)
            raise

        try:
            self.goActual()
            time.sleep(0.1)
            self.rh_svc.servo(jname, SWITCH_ON)
            time.sleep(2)
            if not self.isServoOn(jname):
                print self.configurator_name, 'servo on failed.'
                raise
        except:
            print self.configurator_name, 'exception occured'

        return 1

    def servoOff(self, jname='all', wait=True):
        '''
        @type jname: str
        @param jname: The value 'all' works iteratively for all servos.
        @type wait: bool
        @rtype: int
        @return: 1 = all arm servo off. 2 = all servo on arms and hands off.
                -1 = Something wrong happened.
        '''
        # do nothing for simulation
        if self.simulation_mode:
            print self.configurator_name, 'omit servo off'
            return 0

        print 'Turn off Hand Servo'
        if self.sc_svc:
            self.sc_svc.servoOff()
        # if the servos aren't on switch power off
        if not self.isServoOn(jname):
            if jname.lower() == 'all':
                self.rh_svc.power('all', SWITCH_OFF)
            return 1

        # if jname is not set properly set to all -> is this safe?
        if jname == '':
            jname = 'all'

        if wait:
            waitInputConfirm(
                '!! Robot Motion Warning (Servo OFF)!!\n\n'
                'Push [OK] to servo OFF (%s).' % (jname))  # :

        try:
            self.rh_svc.servo('all', SWITCH_OFF)
            time.sleep(0.2)
            if jname == 'all':
                self.rh_svc.power('all', SWITCH_OFF)

            # turn off hand motors
            print 'Turn off Hand Servo'
            if self.sc_svc:
                self.sc_svc.servoOff()

            return 2
        except:
            print self.configurator_name, 'servo off: communication error'
            return -1

    def checkEncoders(self, jname='all', option=''):
        '''
        Run the encoder checking sequence for specified joints,
        run goActual and turn on servos.

        @type jname: str
        @param jname: The value 'all' works iteratively for all servos.
        @type option: str
        @param option: Possible values are follows (w/o double quote):\
                        "-overwrite": Overwrite calibration value.
        '''
        if self.isServoOn():
            waitInputConfirm('Servo must be off for calibration')
            return
        # do not check encoders twice
        elif self.isCalibDone():
            waitInputConfirm('System has been calibrated')
            return

        self.rh_svc.power('all', SWITCH_ON)
        msg = '!! Robot Motion Warning !!\n'\
              'Turn Relay ON.\n'\
              'Then Push [OK] to '
        if option == '-overwrite':
            msg = msg + 'calibrate(OVERWRITE MODE) '
        else:
            msg = msg + 'check '

        if jname == 'all':
            msg = msg + 'the Encoders of all.'
        else:
            msg = msg + 'the Encoder of the Joint "' + jname + '".'

        try:
            waitInputConfirm(msg)
        except:
            print "If you're connecting to the robot from remote, " + \
                  "make sure tunnel X (eg. -X option with ssh)."
            self.rh_svc.power('all', SWITCH_OFF)
            return 0

        print self.configurator_name, 'calib-joint ' + jname + ' ' + option
        self.rh_svc.initializeJointAngle(jname, option)
        print self.configurator_name, 'done'
        self.rh_svc.power('all', SWITCH_OFF)
        self.goActual()
        time.sleep(0.1)
        self.rh_svc.servo(jname, SWITCH_ON)

        # turn on hand motors
        print 'Turn on Hand Servo'
        if self.sc_svc:
            self.sc_svc.servoOn()

    # ##
    # ## initialize
    # ##

    def init(self, robotname="Robot", url=""):
        '''
        Calls init from its superclass, which tries to connect RTCManager,
        looks for ModelLoader, and starts necessary RTC components. Also runs
        config, logger.
        Also internally calls setSelfGroups().

        @type robotname: str
        @type url: str
        '''
        print self.configurator_name, "waiting ModelLoader"
        self.waitForModelLoader()
        print self.configurator_name, "start hrpsys"

        print self.configurator_name, "finding RTCManager and RobotHardware"
        self.waitForRTCManagerAndRoboHardware(robotname)
        self.sensors = self.getSensors(url)

        print self.configurator_name, "creating components"
        self.createComps()

        print self.configurator_name, "connecting components"
        self.connectComps()

        print self.configurator_name, "activating components"
        self.activateComps()

        print self.configurator_name, "setup logger"
        self.setupLogger()

        print self.configurator_name, "setup joint groups"
        self.setSelfGroups()

        print self.configurator_name, '\033[32minitialized successfully\033[0m'

    def __init__(self, cname="[hrpsys.py] "):
        initCORBA()
        self.configurator_name = cname


if __name__ == '__main__':
    hcf = HrpsysConfigurator()
    if len(sys.argv) > 2:
        hcf.init(sys.argv[1], sys.argv[2])
    elif len(sys.argv) > 1:
        hcf.init(sys.argv[1])
    else:
        hcf.init()
