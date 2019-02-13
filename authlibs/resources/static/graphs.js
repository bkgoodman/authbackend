
makePostCall = function (url, data) { // here the data and url are not hardcoded anymore
   var json_data = JSON.stringify(data);
	// console.log("QERY "+url);
	//console.log(json_data);
    return $.ajax({
        type: "GET",
        url: url,
        data: data,
        dataType: "json",
        contentType: "application/json;charset=utf-8"
    });
	
}


function queryResources(url) {
	makePostCall(url, null)
			.success(function(indata){
				var data = google.visualization.arrayToDataTable(indata['data']);
				var chart;
				if (indata['type']=='pie')
								chart = new google.visualization.PieChart(document.getElementById('chart_div'));
				else
								chart = new google.visualization.AreaChart(document.getElementById('chart_div'));
				
        chart.draw(data, indata['opts']);
		 })
			.fail(function(sender, message, details){
						 console.log("Sorry, something went wrong!",message,details);
		});
}

function graphButton(button,url) {
	console.log(event);
	console.log(url);
	queryResources(url);
}
