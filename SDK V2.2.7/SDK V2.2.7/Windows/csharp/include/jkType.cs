using System;
using System.Collections.Generic;
//using System.Numerics;
using System.Text;
using System.Runtime.InteropServices;


namespace jkType
{

	public class JKTYPE
	{
		/**
        * @brief Cartesian spatial location data type
        */
		[StructLayout(LayoutKind.Sequential)]
		public struct CartesianTran
		{

			public double x;       ///< x-axis coordinate, unit mm
			public double y;       ///< y-axis coordinate, unit mm
			public double z;       ///< z-axis coordinate, unit mm
		};

		/**
		* @brief Euler Angle Attitude Data Type
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct Rpy
		{
			public double rx;      ///< Angle of rotation around fixed axis X, unit ：rad
			public double ry;	   ///< Angle of rotation around fixed axis Y, unit ：rad
			public double rz;      ///< Angle of rotation around fixed axis Z, unit ：rad
		};

		/**
		* @brief Quaternion Gesture Data Type
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct Quaternion
		{
			public double s;
			public double x;
			public double y;
			public double z;
		};

		/**
		*@brief Cartesian space position type
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct CartesianPose
		{
			public CartesianTran tran;     ///< Cartesian space location
			public Rpy rpy;                ///< Cartesian space gesture
		};

		/**
		* @brief Rotated Matrix Data Types
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct RotMatrix
		{
			public CartesianTran x;        ///< x-axis lexile
			public CartesianTran y;		   ///< y-axis lexile
			public CartesianTran z;        ///< z-axis lexile
		};

		/**
		* @brief Program operation status enumeration type
		*/
		public enum ProgramState
		{
			PROGRAM_IDLE,					///< Robot stopped running
			PROGRAM_RUNNING,				///< The robot is running.
			PROGRAM_PAUSED					///< the robot is paused	
		};

		/**
		* @brief Foce control enumeration type
		*/
		public enum FTFrameType
		{
			FTFrame_Tool = 0, 
			FTFrame_World = 1
		};

		/**
		* @brief Coordinate system selection enumeration type
		*/
		public enum CoordType
		{
			COORD_BASE,						///< Base coordinate system
			COORD_JOINT,					///< Joint space
			COORD_TOOL						///< Tool coordinate system
		};

		/**
		* @brief movement pattern enumeration
		*/
		public enum MoveMode
		{
			ABS = 0,						///< Absolute motion
			INCR,							///< incremental motion
			CONTINUE						///< Continuous or extended tool coordinate motion
		};

		/**
		* @brief load data type
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct PayLoad
		{
			public double mass;					///< Load quality, unit：kg
			public CartesianTran centroid;		///< Load center of mass, unit：mm
		};

		/**
		* @brief Joint position
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct JointValue
		{
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public double[] jVal ;												///< unit：rad	
		};

		/**
		* @brief IO type enum
		*/
		public enum IOType
		{
			IO_CABINET, ///< cabinet IO
			IO_TOOL,	///< tool IO
			IO_EXTEND,	///< extend IO
			IO_REALY,   ///< relay IO，only CAB V3 support
			IO_MODBUS_SLAVE, ///< Modbus slave IO, index starts from 0
			IO_PROFINET_SLAVE, ///< Profinet slave IO, index starts from 0
			IO_EIP_SLAVE      ///< ETHRENET/IP slave IO, index starts from 0
		};


		/**
		* @brief robot torque data
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct TorqueValue
		{
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public double[] jTorque;  
		}

		/**
		*@brief Controller User Variable Struct
		*@param id controller inner usage
		*@param value value type always double
		*@param alias variable alias which is less than 100 bytes
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct UserVariable {
			public int id;
			public double value;
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 100)]
			public char[] alias;
		} 

		/**
		* @brief number of UserVariable is fixed to 100
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct UserVariableList{
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 100)]
			public UserVariable[] v;
		} 
	

		/**
		* @brief robot status data
		*/		
		[StructLayout(LayoutKind.Sequential)]
		public struct RobotStatus
		{
			public int errcode;												///< robot errorcode,0:normal
			public int inpos;												///< is inpos or not,0: not in pos,1: in pos
			public int powered_on;											///< power on/off,0: off,1: on
			public int enabled;												///< enable/disable robot,0: disabled,1: enabled
			public double rapidrate;										///< speed ratio
			public int protective_stop;										///< is in collision or not,0: no collision,1: in collision
			public int emergency_stop;										///< is estop or not,0: not in etop,1: in estop
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 256)]
			public int []dout;												///< cabinet DOUT,dout[0] is number of signals
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 256)]
			public int []din;												///< cabinet DIN,din[0] is number of signals
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 256)]
			public double []ain;											///< cabinet AIN,ain[0] is number of signals
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 256)]
			public double []aout;											///< cabinet AOUT,aout[0] is number of signals
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 16)]
			public int[] tio_dout;								        ///< TIO DOUT,tio_dout[0] is number of signals
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 16)]
			public int[] tio_din;										///< TIO DIN,tio_din[0] is number of signals
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 16)]
			public double[] tio_ain;									///< TIO AIN,tio_ain[0] is number of signals
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
			public int[] tio_key;                                		///< tool button,  [0]free;[1]point;[2]pause_resume;
			public Io_group extio;								    		///< extend IO
			public Io_group modbus_slave;									///< Modbus slave
			public Io_group profinet_slave;									///< Profinet slave
			public Io_group eip_slave;										///< Ethernet/IP slave
			public int current_tool_id;										///< current used tool id
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public double[] cartesiantran_position;							///< TCP position
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public double[] joint_position;									///< joint position
			public int on_soft_limit;										///< in softlimit or not,0: not in softlimit,1: in softlimit
			public int current_user_id;										///< current used user_frame id
			public int drag_status;											///< is in drag state or not ,0: not in drag,1: in drag
			public RobotMonitorData robot_monitor_data;                     ///< robot monitor data
			public TorqSensorMonitorData torq_sensor_monitor_data;          ///< torque sensor data
			public int is_socket_connect;									///< not uesed

		}

		/**
		* @brief TRAJ function config
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct TrajTrackPara
		{
			public double xyz_interval;                         ///< cartesian translation acquisition accuracy
			public double rpy_interval;                         ///< cartesian orientation acquisition accuracy
			public double vel;                                  ///< velocity setting for scripty execution
			public double acc;                                  ///< acceleration setting for scripty execution
		}

		/**
		* @brief not used
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct OptionalCond
		{
			public int executingLineId;                                ///< 
		}

		/**
		* @brief admittance config param
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct AdmitCtrlType
		{
			public int opt;             ///< 0: disable, 1: enable
			public double ft_user;      ///< the force value to let robot move in MAX velocity, also naming as ft_damping
			public double ft_rebound;   ///< rebound force, ability for robot to go back to init position
			public double ft_constant;  ///< constant force
			public int ft_normal_track; ///< normal vector track，0: disable，1: enable. deprecated, cannot set any more(always disabled)
		}

		/**
		* @brief robot admittance control configs collection
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct RobotAdmitCtrl
		{
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public AdmitCtrlType[] admit_ctrl;
		}

		/**
		* @brief velocity force control setting
		* there are 3 levels to set，and 1>rate1>rate2>rate3>rate4>0
		* at level 1，able to set rate1,rate2。rate3 and rate4, both are 0
		* at level 2，able to set rate1,rate2，rate3. rate4 is 0
		* at level 3，able to set rate1,rate2，rate3,rate4
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct VelCom
		{
			public int vc_level;                                         //velocity force control level setting
			public double rate1;                                         //
			public double rate2;                                         //
			public double rate3;                                         //
			public double rate4;                                         //
		}

		/**
		* @brief force control components
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct FTxyz
		{
			public double fx;                                           // x component
			public double fy;                                           // y component
			public double fz;                                           // z component
			public double tx;                                           // rx component
			public double ty;                                           // ry component
			public double tz;                                           // rz component
		}

		/**
		*  @brief DH
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct DHParam
		{
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public double[] alpha;
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public double[] a;
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public double[] d;
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public double[] joint_homeoff;
		}

		[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
		public struct SignInfo{
			[MarshalAs(UnmanagedType.ByValTStr, SizeConst = 20)]
			public string sig_name;//name
			public int chn_id;		//RS485 channel ID
			public int sig_type;	//signal type
			public int sig_addr;	//address
			public int value;		//value
			public int frequency;	//must less than 20
		}

		[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
		public struct SignInfo_simple{
			[MarshalAs(UnmanagedType.ByValTStr, SizeConst = 20)]
			public string sig_name;//name
			public int frequency;	//must less than 20
		}

		[StructLayout(LayoutKind.Sequential)]
		public struct ModRtuComm
		{
			public int chn_id;		//RS485 channel ID
			public int slaveId;		//slave station id, only used with Modbus RTU
			public int baudrate;	//4800,9600,14400,19200,38400,57600,115200,230400
			public int databit;		//7，8
			public int stopbit;		//1，2
			public int parity;		//78->no check, 79->odd parity check, 69->even parity check
		}

		/**
		* @brief torque sensor data
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct TorqSensorData
		{
			public int status;
			public int errorCode;
			public FTxyz data;
		}

		[StructLayout(LayoutKind.Sequential)]
		public struct ForceStopCondition{
			public int opt; // 0:disable, 1:enable
			public int axis;

			public int lower_limit_opt;
			public double lower_limit;

			public int upper_limit_opt;
			public double upper_limit;

		} 

		[StructLayout(LayoutKind.Sequential)]
		public struct ForceStopConditionList{
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public ForceStopCondition[] condition;

		} 

		/**
		* @brief tool drive config
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct ToolDriveConfig
		{
			public int opt;			///< 0: disable, 1: enable
			public int axis;			///< axis index, [0,5]
			public double rebound;	 	///< rebound ability
			public double rigidity;	///< 
		}

		/**
		* @brief 
		*/
		[StructLayout(LayoutKind.Sequential)]
		public struct RobotToolDriveCtrl
		{
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public ToolDriveConfig[] config;
		} 

		[StructLayout(LayoutKind.Sequential)]
		public struct RobotState{
			public int estoped;     // estop
			public int poweredOn;		// power on
			public int servoEnabled;	// enable robot or not
		}

		[StructLayout(LayoutKind.Sequential)]
		public struct RobotStatus_simple
		{
			public int errcode;	///< 0: normal, others: errorcode

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 200)]
			public char[] errmsg; ///< controller errmsg
			
			public int powered_on;	///< 0: power off，1: power on
			public int enabled;	///< 0: disabled，1: enabled
		} 

		[StructLayout(LayoutKind.Sequential)]	
		public struct DragFrictionCompensationGainList
		{
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public int[] gain; 
		} 

		public enum  ProcessType{
			MOT_KEEP = 0,  ///< no change
			MOT_PAUSE, ///< pause
			MOT_ABORT  ///< abort
		}

		[StructLayout(LayoutKind.Sequential)]
		public struct ErrorCode
		{
			public long code;		   ///< error code

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 120)]
			public char[] message; ///< error message
		}

		[StructLayout(LayoutKind.Sequential)]
		public struct  ProgramInfo{
			public int logic_line;             ///< program script executing line
			public int motion_line;            ///< executing motion CMD id

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 100)]
			public char[] file;             ///< current program file

			public ProgramState program_state; ///< program executing state
		};

		[StructLayout(LayoutKind.Sequential)]
		public struct MultStrStorType
		{
			public int len;										///< size
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 128*128)]
			public char[] name ;                              ///< data array
		}

		[StructLayout(LayoutKind.Sequential)]
		public struct Io_group
		{
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 256)]
			public int[] din;				  ///< Digital input din[0] is the number of valid signals

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 256)]
			public int[] dout;				  ///< Digital output dout[0] is the number of valid signals

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 256)]
			public float[] ain;				  ///< Analog input din[0] is the number of valid signals

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 256)]
			public float[] aout;			  ///< Analog output dout[0] is the number of valid signals
		} ;

		[StructLayout(LayoutKind.Sequential)]
		public struct JointMonitorData
		{
			public double instCurrent;		///< Instantaneous current
			public double instVoltage;		///< Instantaneous voltage
			public double instTemperature; ///< Instantaneous temperature
			public double instVel;			///< Instantaneous speed controller 1.7.0.20 and above
			public double instTorq;		///< Instantaneous torque
		};

		[StructLayout(LayoutKind.Sequential)]
		public struct RobotMonitorData
		{
			public double scbMajorVersion;				  ///< scb major version number
			public double scbMinorVersion;				  ///< scb minor version number
			public double cabTemperature;				  ///< Controller temperature
			public double robotAveragePower;			  ///< Robot average voltage
			public double robotAverageCurrent;			  ///< Robot average current

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public JointMonitorData[] jointMonitorData; ///< Monitoring data of the robot's six joints
		};

		[StructLayout(LayoutKind.Sequential)]
		public struct TorqSensorMonitorData
		{
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 20)]
			public char[] ip;		 ///< Torque sensor IP address

			public int port;			 ///< Torque sensor port number
			public PayLoad payLoad;	 ///< Tool load
			public int status;			 ///< Torque sensor status
			public int errcode;		 ///< Torque sensor abnormal error code

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public double[] actTorque; ///< The actual contact force value of the torque sensor (when Initialize is checked) or the raw reading value (when Do Not Initialize is checked)
			
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public double[] torque;	 ///< Torque sensor raw reading value

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public double[] realTorque;///< The actual contact force value of the torque sensor (does not change with the initialization options)
		};


		[StructLayout(LayoutKind.Sequential)]
		public struct JointVelocity
		{
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public double[] jVel; // each joint, unit: rad/s
		}

		[StructLayout(LayoutKind.Sequential)]
		public struct JointTorque
		{
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)]
			public double[] jtorq; // each joint torque, unit: N/m
		}

		[StructLayout(LayoutKind.Sequential)]
		public struct EdgIOState
		{
			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 16)]
			public int[] cab_din;

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 16)]
			public int[] cab_dout;

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 2)]
			public double[] cab_ain;

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 2)]
			public double[] cab_aout;

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 2)]
			public int[] tool_din;

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 2)]
			public int[] tool_dout;

			[MarshalAs(UnmanagedType.ByValArray, SizeConst = 2)]
			public double[] tool_ain;
		}

		[StructLayout(LayoutKind.Sequential)]
		public struct EDGState
		{
			public JointValue jointVal; // each joint position, unit: rad
			public JointVelocity jointVel; // each joint velocity, unit: rad/s
			public JointTorque jointTorq; // each joint torque, unit: N/m
			public CartesianPose cartpose;
			public FTxyz torqSensor;
			public EdgIOState IOState;
		}
		
		[StructLayout(LayoutKind.Sequential)]
		public struct MotionStatus
		{
			public int motion_line;          // motion CMD id
			public int motion_line_sdk;      // reserved
			public bool inpos;               // current motion CMD is done, you should always check queue info at the same time
			public bool err_add_line;        // fail to add motion CMD in case robot is already at target position
			public int queue;                // number of motion CMD in queue
			public int active_queue;         // number of motion CMD which is under blending
			public bool queue_full;          // cannot push any more motion CMD if queue is full
			public bool paused;              // paused state
			public bool isOnLimit;           // soft limit
			public bool isInEstop;           // emergency stop
			public bool isInCollision;       // collision
		}

	}
}
