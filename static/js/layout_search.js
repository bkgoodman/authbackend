
function layout_search_keypress(){
  $('#layout_search_menu').dropdown('toggle');
	line = $("#layout_search_text")[0].value;
	if (line == "") {
   $('#layout_search_menu').removeClass('open');
   $('#layout_search_menu').removeClass('show');
	return;
}

	makePostCall = function (url, data) { // here the data and url are not hardcoded anymore
		 var json_data = JSON.stringify(data);
			return $.ajax({
					type: "GET",
					url: url,
					data: data,
					dataType: "json",
					contentType: "application/json;charset=utf-8"
			});
	}
	makePostCall(LAYOUT_SEARCH_URL+line, "")
		.success(function(data){
			var x = $(".layout_search_item")[0]
			while (x)  {
				x.parentNode.removeChild(x);
				var x = $(".layout_search_item")[0]
			}
			var lst = $("#layout_search_menu")[0]
			for (x in data){ 
				el = document.createElement("a");
				el.setAttribute("data-target",data[x]['url'])
				el.setAttribute("href",data[x]['url'])
				el.className="dropdown-item layout_search_item nav-item nav-link";
				el.innerHTML = data[x]['title'];
				lst.appendChild(el);
			}
$( ".layout_search_item" ).on('click',function(event) {
  console.log(event.target.href);
	window.location=event.target.href;
});
		})
		.fail(function(sender, message, details){
						 
		});
}




function layout_search_blur() {
  // $('#layout_search_menu').removeClass('open');
  // $('#layout_search_menu').removeClass('show');
  // $('#layout_search_text')[0].value="";
}
