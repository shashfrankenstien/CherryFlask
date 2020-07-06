
def HTML(content, title):
	return '''
	<!DOCTYPE html>
	<html lang="en">
		<head>
			<meta charset="UTF-8">
			<meta name="viewport" content="width=device-width, initial-scale=1.0">
			<title>{}</title>
		</head>
		<body>
			{}
		</body>
	</html>'''.format(title, str(content))

def H(index, content):
	return "<h{i}>{c}</h{i}>".format(c=content, i=index)

def DIV(content, css=[]):
	if not isinstance(css, (list,set,tuple)):
		css = [css]
	if css:
		return "<div class='{}'>{}</div>".format(' '.join(css), content)
	else:
		return "<div>{}</div>".format(content)

def TABLE(thead='', tbody='', css=[]):
	if not isinstance(css, (list,set,tuple)):
		css = [css]
	if css:
		return "<table class='{}'>{}{}</table>".format(' '.join(css), thead, tbody)
	else:
		return "<table>{}{}</table>".format(thead, tbody)

def THEAD(headers):
	th = ["<th>{}</th>".format(h) for h in headers]
	return "<thead>{}</thead>".format(''.join(th))

def TBODY(rows):
	return "<tbody>{}</tbody>".format(''.join(rows))

def TD(content, css=[], colspan=1, rowspan=1):
	if not isinstance(css, (list,set,tuple)):
		css = [css]
	return "<td class='{}' colspan={} rowspan={}>{}</td>".format(
		' '.join(css),
		colspan,
		rowspan,
		content
	)

def TR(row):
	return "<tr>{}</tr>".format(''.join(row))

def SCRIPT(s):
	return "<script>{}</script>".format(s)


class ReadOnlyTaskMonitor(object):

	STYLES = '''
		<style>
			body {
				width:100%;
				height:100%;
				margin: 0;
				display:flex;
				flex-direction:column;
				align-items:center;
			}
			h2 { padding-top:10px;}
			table {
				border-spacing: 5px;
				border-collapse: collapse;
				border: 1px solid black;
				width:70%;
				margin-top:20px;
			}
			td, th {
				border: 1px solid black;
				padding: 5px;
			}
			th {
				height:2vh;
				background-color:#3d3d3d;
				color:white;
			}
			td.grey {color:#c2c2c2;}
			td.yellow {background-color:yellow;}
			td.green {
				background-color:#d2ffcc;
				color:green;
			}
			td.red {
				background-color:red;
				color:white;
				font-weight:bold;
			}
			a > button {
				width:100%;
				height:100%;
				cursor:pointer;
			}
			.container {
				width:100%;
				height:100%;
				display:flex;
				flex-direction:row;
			}
			.monitor {
				width: 30vw;
				height: 100vh;
				display:flex;
				flex-direction:column;
				align-items:center;
			}
			.monitor > div {
				width:90%;
				overflow-wrap: break-word;
			}
			.logs_div {
				width: 70vw;
				height: 100vh;
				display:flex;
				align-items:center;
				justify-content:center;
			}
			.info_table {
				border:none;
				margin-bottom:20px;
				width:100%;
			}
			.info_table td {
				border:none;
				width:50%;
				text-align:left;
			}
			td.title {
				font-weight:bold;
				text-align:right !important;
				padding-right:20px;
			}
			.log_table {
				table-layout:fixed;
				width:97%;
				height:96vh;
				margin-top:0px;
				overflow:hidden;
			}
			.log_table td {
				vertical-align: top;
				overflow:hidden;
			}
			.console {
				background-color:#3d3d3d;
				color:white;
			}
			.log_table td.console > div {
				width:100%;
				height:92vh;
				scrollbar-color: grey #3d3d3d;
				overflow-anchor: none;
				overflow:scroll;
				white-space: nowrap;
				list-style-type: none;
				font-family: 'Roboto Mono', monospace;
				font-size: 14px;
				padding-left: 5px;
			}
			.anchor-div {
				width:100%;
				overflow-anchor: auto;
				height: 1px;
			}
		</style>
		'''

	def __init__(self, app, sched, endpoint="@taskmonitor", display_name=None):
		self.app = app
		self.sched = sched
		self._endpoint = endpoint
		self._display_name = display_name or self.app.name
		self.create_endpoints()

	def create_endpoints(self):
		self.app.add_url_rule("/{}".format(self._endpoint), view_func=self.__show_all, methods=['GET'])
		self.app.add_url_rule("/{}/<int:n>".format(self._endpoint), view_func=self.__show_one, methods=['GET'])

	def __html_wrap(self, *args):
		return HTML(''.join(args), title="{} Task Monitor".format(self._display_name))

	def __job_state(self, jdict):
		state = 'READY'
		if jdict['is_running']:
			state = "RUNNING"
		elif jdict['logs']['err'].strip()!='':
			state = "ERROR"
		elif jdict['logs']['end'] is not None and jdict['logs']['log'].strip()!='':
			state = "SUCCESS"
		return state

	def __job_state_css(self, state):
		css = []
		if state=="READY":
			css = 'grey'
		elif state=="RUNNING":
			css = 'yellow'
		elif state=="ERROR":
			css = 'red'
		elif state=="SUCCESS":
			css = 'green'
		return css

	def __job_duration(self, jdict):
		duration = None
		if jdict['logs']['start'] is not None and jdict['logs']['end'] is not None:
			duration = jdict['logs']['end']-jdict['logs']['start']
		return duration

	def __job_schedule_str(self, jdict):
		return "every {} seconds".format(jdict['every']) if isinstance(jdict['every'], int) else "every {} at {}".format(jdict['every'], jdict['at'])

	def __job_dictlist_to_html(self, d):
		rows = []
		for row in d:
			tds = []
			for cell in row.values():
				if isinstance(cell, dict):
					cell = self.__job_dictlist_to_html([cell])
				if cell is None:
					cell = '-'

				cell_str = str(cell).replace("\n", "<br>")
				tds.append(TD(cell_str, self.__job_state_css(cell_str)))
			rows.append(TR(tds))
		return TABLE(thead=THEAD(d[0].keys()), tbody=TBODY(rows))

	def __show_all(self):
		d = []
		for i,j in enumerate(self.sched.jobs):
			jd = j.to_dict()
			duration = self.__job_duration(jd)
			state = self.__job_state(jd)
			d.append({
				'Id': i,
				'Name': jd['func'],
				'Schedule': self.__job_schedule_str(jd),
				'Description': jd['doc'].strip().split('\n')[0] + "..." if jd['doc'] is not None else '-',
				'State': state,
				'Time Taken': duration,
				'Next Run': jd['next_run'],
				'More':"<a href='/{}/{}'><button>show more</button><a>".format(self._endpoint, i)
			})

		auto_reload_script = '''
		window.addEventListener('load', (event) => {{
			setTimeout(()=>location.reload(), 5000)
		}})
		'''
		return self.__html_wrap(
			self.STYLES,
			H(2, "{} - Task Monitor".format(self._display_name)),
			self.__job_dictlist_to_html(d),
			SCRIPT(auto_reload_script)
		)

	def __show_one(self, n):
		jobd = self.sched.jobs[n].to_dict()
		htmlify_text = lambda t: str(t).strip().replace("\n", "<br>").replace("\t", "&#9;").replace(' ', '&nbsp;')
		titleTD = lambda t: TD(t, 'title')
		modTD = lambda t,css=[]: TD("-" if t is None else t, css)
		state = self.__job_state(jobd)
		rows = [
			TR([ titleTD("Schedule"), TD(self.__job_schedule_str(jobd)), ]),
			TR([ titleTD("State"), modTD(state, self.__job_state_css(state)) ]),
			TR([ titleTD("Time Taken"), modTD(self.__job_duration(jobd)) ]),
			TR([ titleTD("Next Run In"), "<td id='next-run-in'>-<td>" ]),
		]
		info_table = TABLE(tbody=TBODY(rows), css='info_table')
		description_div = DIV(htmlify_text(jobd['doc'])) if jobd['doc'] is not None else ''
		monitor_div = DIV(
			H(2, jobd['func']) + info_table + description_div,
			css="monitor"
		)

		logs_row = TR([
			TD( DIV( htmlify_text(jobd['logs']['log']) + DIV('', css='anchor-div') ), css="console"),
			TD( DIV( htmlify_text(jobd['logs']['err']) + DIV('', css='anchor-div') ), css="console"),
		])

		logs_table = TABLE(thead=THEAD(['Logs', 'Traceback']), tbody=TBODY(logs_row), css='log_table')
		logs_div = DIV( logs_table, css="logs_div" )

		container = DIV(
			monitor_div + logs_div,
			css="container"
		)

		auto_reload_script = '''
		let running = {}
		let next_run = Date.parse("{}")
		window.addEventListener('load', (event) => {{
			if (running) {{
				setTimeout(()=>location.reload(), 3000)
			}} else if ( isNaN(next_run) ) {{
				document.getElementById("next-run-in").innerHTML = 'Never'
			}} else {{
				setInterval(()=>{{
					let ttr = next_run-Date.now()
					if (ttr<=0) {{
						location.reload()
					}} else {{
						let zd = new Date(0)
						zd.setSeconds(Math.round(ttr/1000))
						document.getElementById("next-run-in").innerHTML = zd.toISOString().substr(11, 8)
					}}
				}}, 1000)
			}}
		}});
		'''.format(int(jobd['is_running']), jobd['next_run'])

		return self.__html_wrap(
			self.STYLES,
			container,
			SCRIPT(auto_reload_script)
		)
