# Filter MSA with ground truth

> Author: Anonymous
> 
> Email: Anonimous

Starting from [this dataset of MSA application from Rahman et al.](https://github.com/davidetaibi/Microservices_Project_List),
the repos has been filtered keeping only those with a ground truth on the microservices, i.e. those that have a list of
its microservices documented somewhere (README, wiki, other related documentation).

<hr>

> reference date: 16/02/2024

Actual filtering results: 

| REPO                                                                            | Ground truth |
|---------------------------------------------------------------------------------|:------------:|
| https://github.com/acmeair/                                                     |              |
| https://github.com/oktadeveloper/spring-boot-microservices-example              |              |
| https://github.com/fernandoabcampos/spring-netflix-oss-microservices            |              |
| https://github.com/ArcanjoQueiroz/cas-microservice-architecture                 |              |
| https://github.com/Crizstian/cinema-microservice/tree/step-1?tab=readme-ov-file |              |
| https://github.com/benwilcock/cqrs-microservice-sampler                         |              |
| https://github.com/kbastani/cloud-native-microservice-strangler-example         |   &#10003;   |
| https://github.com/citerus/dddsample-core                                       |              |
| https://github.com/matt-slater/delivery-system                                  |              |
| https://github.com/digota/digota                                                |              |
| https://github.com/venkataravuri/e-commerce-microservices-sample                |              |
| https://github.com/ExplorViz                                                    |              |
| https://github.com/gfawcett22/EnterprisePlanner                                 |              |
| https://github.com/dotnet-architecture/eShopOnContainers                        |              |
| https://github.com/william-tran/freddys-bbq                                     |              |
| https://github.com/microservices-patterns/ftgo-application                      |   &#10003;   |
| https://github.com/xJREB/research-modifiability-pattern-experiment              |              |
| https://github.com/kbastani/spring-boot-graph-processing-example                |   &#10003;   |
| https://github.com/GoogleCloudPlatform/microservices-demo                       |              |
| https://github.com/jaegertracing/jaeger/tree/master/examples/hotrod             |              |
| https://github.com/TheDigitalNinja/million-song-library                         |              |
| https://github.com/Microservice-API-Patterns/LakesideMutual                     |   &#10003;   |
| https://github.com/idugalic/micro-company                                       |   &#10003;   |
| https://github.com/senecajs/ramanujan                                           |              |
| https://github.com/bishion/microService                                         |              |
| https://github.com/ewolff/microservice                                          |   &#10003;   |
| https://github.com/mspnp/microservices-reference-implementation                 |              |
| https://github.com/bishion/microService                                         |              |
| https://github.com/mdeket/spring-cloud-movie-recommendation                     |              |
| https://github.com/aspnet/MusicStore                                            |              |
| https://github.com/SteeltoeOSS/Samples/tree/master/MusicStore                   |              |
| https://github.com/yidongnan/spring-cloud-netflix-example                       |              |
| https://github.com/microsoft/PartsUnlimitedMRPmicro                             |              |
| https://github.com/nginxinc/mra-ingenious                                       |              |
| https://github.com/sqshq/PiggyMetrics                                           |   &#10003;   |
| https://github.com/EdwinVW/pitstop                                              |   &#10003;   |
| https://github.com/callistaenterprise/blog-microservices                        |              |
| https://github.com/instana/robot-shop                                           |              |
| https://github.com/antonio94js/servicecommerce                                  |              |
| https://github.com/JoeCao/qbike                                                 |              |
| https://github.com/sitewhere/sitewhere                                          |              |
| https://github.com/microservices-demo                                           |              |
| https://github.com/zpng/spring-cloud-microservice-examples                      |              |
| https://github.com/paulc4/microservices-demo                                    |              |
| https://github.com/spring-petclinic/spring-petclinic-microservices              |   &#10003;   |
| https://github.com/aws-samples/amazon-ecs-java-microservices                    |              |
| https://github.com/oktadeveloper/spring-boot-microservices-example              |              |
| https://github.com/sivaprasadreddy/spring-boot-microservices-series             |   &#10003;   |
| https://github.com/Staffjoy/V2                                                  |              |
| https://github.com/LandRover/StaffjoyV2                                         |              |
| https://github.com/jferrater/Tap-And-Eat-MicroServices                          |   &#10003;   |
| https://github.com/yun19830206/CloudShop-MicroService-Architecture              |              |
| https://github.com/DescartesResearch/TeaStore/wiki                              |              |
| https://github.com/FudanSELab/train-ticket/                                     |   &#10003;   |
| https://github.com/Vanilla-Java/Microservices                                   |              |
| https://github.com/mohamed-abdo/vehicle-tracking-microservices                  |              |
| https://github.com/HieJulia/warehouse-microservice                              |              |
| https://github.com/daxnet/we-text                                               |              |

<hr>

Being that the repos in this dataset are often used in literature as benchmark, from the remaining repos those with at 
least 10 references in literature - and at least 100 commits - have been chosen (searching with their url in google 
Scholar).

<hr>

> reference date: 16/02/2024

Actual results: 

| REPO                                                                            | # of commits | # of references | \>10 ref and \>200 commits \? |
|---------------------------------------------------------------------------------|:------------:|:---------------:|:-----------------------------:|
| https://github.com/kbastani/cloud-native-microservice-strangler-example         |      15      |        2        |                               |
| https://github.com/microservices-patterns/ftgo-application                      |     295      |       20        |           &#10003;            |
| https://github.com/kbastani/spring-boot-graph-processing-example                |      35      |        3        |                               |
| https://github.com/Microservice-API-Patterns/LakesideMutual                     |      22      |       38        |                               |
| https://github.com/idugalic/micro-company                                       |     261      |        6        |                               |
| https://github.com/ewolff/microservice                                          |     140      |       17        |           &#10003;            |
| https://github.com/sqshq/PiggyMetrics                                           |     290      |       36        |           &#10003;            |
| https://github.com/EdwinVW/pitstop                                              |     140      |       11        |           &#10003;            |
| https://github.com/spring-petclinic/spring-petclinic-microservices              |     727      |       43        |           &#10003;            |
| https://github.com/sivaprasadreddy/spring-boot-microservices-series             |      13      |        1        |                               |
| https://github.com/jferrater/Tap-And-Eat-MicroServices                          |      35      |        9        |                               |
| https://github.com/FudanSELab/train-ticket/                                     |     323      |       119       |           &#10003;            |
