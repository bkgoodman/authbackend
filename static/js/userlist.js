
makePostCall = function (url, data) { // here the data and url are not hardcoded anymore
   var json_data = JSON.stringify(data);
    return $.ajax({
        type: "GET",
        url: url,
        data: json_data,
        dataType: "json",
        contentType: "application/json;charset=utf-8"
    });
	
}

function DoSearchButton() {
	changedDropdownText();
}

function DoAllButton() {
	queryMembers("*");
}

// and here a call example
function changedDropdownText() {
	searchstr=document.getElementById("searchfield1").value;
	if (searchstr.length >= 3) {
		document.getElementById("entermatchtext").setAttribute("style","display:none");
		document.getElementById("membertable").setAttribute("style","display:table");
	} else {
		document.getElementById("entermatchtext").setAttribute("style","display:block");
		document.getElementById("membertable").setAttribute("style","display:none");
		return;
	}
	queryMembers(searchstr);
}

function queryMembers(searchstr) {
makePostCall(MEMBER_SEARCH_URL+searchstr, {})
    .success(function(data){

					lst=document.getElementById("memberrows");

					var x = lst.getElementsByClassName("memberrow")[0];
					while(x) {
						x.parentNode.removeChild(x);
						x = lst.getElementsByClassName("memberrow")[0];
					}

					for (x in data){ 
						el = document.createElement("tr");
						el.innerHTML = "<tr>"
						if (USE_MEMBER_CHECKBOXES)
							el.innerHTML += "<td><input type=\"checkbox\" onchange=\"click_checkbox();\" class=\"auth_user_cb\" /></td>";
						td=""
						if (MEMBER_URL) {
							td += "<a href=\""+MEMBER_URL+data[x]['member']+"\">";
						}
						td += data[x]['member'];
						if (MEMBER_URL)
							td +="</a>";
						el.innerHTML += "<td>"+td+"</td>";
						el.innerHTML +=
							"<td>"+data[x]['firstname']+"</td>"+
							"<td>"+data[x]['lastname']+"</td>"+
							"<td>"+data[x]['email']+"</td>"+
							"<td>";
						el.innerHTML += "<a href=\""+MEMBER_URL+data[x]['member']+"\">"+
						 "<img style=\"height:16px\" src=\""+STATIC_URL+"logicon.png\" />"+
						 "</a>";
						el.innerHTML += "&nbsp;<a href=\""+MEMBER_URL+data[x]['member']+"\">"+
						 "<img style=\"height:16px\" src=\""+STATIC_URL+"eye.png\" />"+
						 "</a>";
						el.innerHTML += "<a href=\""+MEMBER_URL+data[x]['id']+"/access\">"+
						 "&nbsp;<img style=\"height:16px\" src=\""+STATIC_URL+"lock.png\" />"+
						 "</a>";
						el.innerHTML += "<a href=\""+MEMBER_URL+data[x]['id']+"/edit\">"+
						 "&nbsp;<img style=\"height:16px\" src=\""+STATIC_URL+"edit.png\" />"+
						 "</a>";
						el.innerHTML += "</td>"+
							"</tr>";
						el.classList.add("memberrow");
						lst.appendChild(el);
					}
    			//lstb.appennd(document.CreateNode("a",<a class="dropdown-item" href="#">Action</a>"
	
	
   })
    .fail(function(sender, message, details){
           console.log("Sorry, something went wrong!",message,details);
  });

}

function click_checkbox() {
	var x = document.querySelectorAll(".auth_user_cb")
	var memexist=false;
	for (i=0;i<x.length;i++) {
		if (x[i].checked) memexist=true;
	}

	var x = document.querySelectorAll(".auth_resource_cb")
	var resexist=false;
	for (i=0;i<x.length;i++) {
		if (x[i].checked) resexist=true;
	}
	btn = document.getElementById("authorize-button");
	if (memexist && resexist) {
		btn.removeAttribute("disabled");
		}
	else {
		btn.setAttribute("disabled",true);
		}
}



function authbutton() {
	var formdata = document.getElementById("formdata");
	var e  = formdata.querySelector("input");
	formdata.innerHTML="";
	/* TODO REMOVEME 
	while (e) {
		elm.removeChild(x);
		var e  = formdata.querySelector("input");
	};
	*/
	var el = document.createElement("input");
	el.innerHTML = "<input type=\"hidden\" name=\"authorize\""+
			"value=\"yes\" />";
	document.getElementById('formdata').appendChild(el);


	var xx = document.getElementById("modaltext");
	xx.innerHTML="Sure you want to authorize ";
	lst=document.getElementById("memberrows");

	var first=true;
	var num=0;
	for (i=0; i< lst.getElementsByClassName("memberrow").length;i++) {
		elm=lst.getElementsByClassName("memberrow")[i];
		td = elm.querySelectorAll("td");
		ch = td[0].childNodes[0];
		if (ch.checked) {
			if (!first)
				xx.innerHTML += ", "
			xx.innerHTML += td[2].innerHTML;
			xx.innerHTML += " "
			xx.innerHTML += td[3].innerHTML;
			first=false;

			var el = document.createElement("input");
			el.innerHTML = "<input type=\"hidden\" name=\"memberid_"+num+"\""+
				"value=\""+td[1].innerHTML+"\" />";
			document.getElementById('formdata').appendChild(el);
			num += 1;
		}
	}

	xx.innerHTML += " on "
	var first=true;
	var num=0;
	lst=document.getElementById("resourcerows");
	for (i=0; i< lst.getElementsByClassName("resourcerow").length;i++) {
		elm=lst.getElementsByClassName("resourcerow")[i];
		td = elm.querySelectorAll("td");
		ch = td[0].childNodes[0];
		if (ch.checked) {
			if (!first)
				xx.innerHTML += ", "
			xx.innerHTML += td[1].innerHTML;
			first=false;

			var el = document.createElement("input");
			el.innerHTML = "<input type=\"hidden\" name=\"resource_"+num+"\" "+
				"value=\""+td[1].innerHTML+"\" />";
			document.getElementById('formdata').appendChild(el);
			num += 1;

		}
	}

	xx.innerHTML += "?"
}
